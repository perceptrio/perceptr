"""
Extract keyframe screenshots from rrweb session (simple processing).

Uses Playwright to load a minimal replay HTML, inject events, seek to each
key timestamp, and take a screenshot. No Node required; single HTML + CDN rrweb.
"""

from __future__ import annotations

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# Keyframe selection
DEFAULT_MAX_FRAMES = 8  # Reduced from 12 for cost optimization
DEFAULT_INTERVAL_S = 20.0
DELAYED_CAPTURE_AFTER_CLICK_S = 1.0  # Capture result of click
DELAYED_CAPTURE_AFTER_SUBMIT_S = 0.5  # Capture success state


def get_keyframe_timestamps(
    normalized_events: list[dict[str, Any]],
    *,
    max_frames: int = DEFAULT_MAX_FRAMES,
    interval_s: float = DEFAULT_INTERVAL_S,
    at_navigations: bool = True,
    at_network_post_200: bool = True,
) -> list[float]:
    """
    Pick timestamps (seconds since start) at which to capture screenshots.

    Strategy: first (0), last, every interval_s, plus at every "user navigated to",
    and at every "network: POST ... 200" (form submit). Then dedupe and cap at max_frames.
    """
    if not normalized_events:
        return []
    first_t = normalized_events[0].get("t", 0.0)
    last_t = normalized_events[-1].get("t", 0.0)

    timestamps: set[float] = {first_t, last_t}

    # Every interval_s
    t = first_t
    while t < last_t:
        timestamps.add(round(t, 1))
        t += interval_s

    # At navigations and form submits (from event text)
    for ev in normalized_events:
        e = ev.get("e", "")
        t = ev.get("t", 0)
        if at_navigations and e.startswith("user navigated to "):
            timestamps.add(round(t, 1))
        if at_network_post_200 and "network:" in e and "POST" in e and "200" in e:
            timestamps.add(round(t, 1))
            # Capture AFTER submit to see success/error state
            delayed_t = t + DELAYED_CAPTURE_AFTER_SUBMIT_S
            if delayed_t <= last_t:
                timestamps.add(round(delayed_t, 1))
        if e.startswith("user click on"):
            timestamps.add(round(t, 1))
            # Capture AFTER click to see result of the action
            delayed_t = t + DELAYED_CAPTURE_AFTER_CLICK_S
            if delayed_t <= last_t:
                timestamps.add(round(delayed_t, 1))
        if e.startswith("user double-click on"):
            timestamps.add(round(t, 1))
        if e.startswith("user right-click on"):
            timestamps.add(round(t, 1))
        if e.startswith("user input on"):
            timestamps.add(round(t, 1))
        if e.startswith("user set to checked"):
            timestamps.add(round(t, 1))
        if e.startswith("user set to unchecked"):
            timestamps.add(round(t, 1))

    ordered = sorted(timestamps)
    # Thin out if over max_frames: keep first, last, and spread the rest
    if len(ordered) <= max_frames:
        return ordered
    step = (len(ordered) - 2) / (max_frames - 2) if max_frames > 2 else 0
    indices = (
        [0] + [int(1 + step * i) for i in range(1, max_frames - 1)] + [len(ordered) - 1]
    )
    return [ordered[i] for i in indices]


def _extract_keyframes_impl(
    events: list[dict],
    keyframe_timestamps: list[float],
    output_dir: Path,
    html_path: Path,
    viewport_width: int,
    viewport_height: int,
) -> list[tuple[float, str]]:
    """Run sync Playwright in a thread to avoid "Sync API inside asyncio loop" (e.g. Jupyter)."""
    from playwright.sync_api import sync_playwright

    results: list[tuple[float, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            ignore_https_errors=True,
        )
        page = context.new_page()

        page.goto(f"file://{html_path.resolve()}")
        page.evaluate(f"window.__RRWEB_EVENTS__ = {json.dumps(events)}")
        page.evaluate("window.__initReplay__()")
        page.wait_for_function("window.__REPLAYER_READY__ === true", timeout=150000)

        for time_s in keyframe_timestamps:
            time_ms = int(time_s * 1000)
            ok = page.evaluate(f"window.__seekTo__({time_ms})")
            if not ok:
                continue
            time.sleep(0.3)
            path = output_dir / f"frame_{time_s:.1f}.png"
            try:
                replayer_el = page.query_selector(
                    "#replayer iframe"
                ) or page.query_selector("#replayer")
                if replayer_el:
                    replayer_el.screenshot(path=str(path))
                else:
                    page.screenshot(path=str(path))
                results.append((time_s, str(path)))
            except Exception:
                continue

        context.close()
        browser.close()

    return results


def extract_keyframes(
    raw_session: dict[str, Any],
    keyframe_timestamps: list[float],
    output_dir: str | Path,
    *,
    viewport_width: int = 1280,
    viewport_height: int = 720,
    replay_html_path: str | Path | None = None,
) -> list[tuple[float, str]]:
    """
    Render rrweb replay at each keyframe timestamp and save screenshots.

    Runs Playwright in a separate thread so it works inside asyncio (e.g. Jupyter).
    raw_session: { "sessionId", "startTime", "endTime", "data": [events] }
    keyframe_timestamps: list of time_s (seconds since session start)
    output_dir: directory to write PNGs (frame_0.0.png, frame_20.5.png, ...)
    Returns: list of (time_s, image_path)
    """
    events = raw_session.get("data", [])
    if not events:
        return []
    full_snapshot = [e for e in events if e.get("type") == 2]
    rest = [e for e in events if e.get("type") != 2]
    if full_snapshot:
        events = full_snapshot + sorted(rest, key=lambda e: e.get("timestamp", 0))

    script_dir = Path(__file__).resolve().parent
    html_path = (
        Path(replay_html_path) if replay_html_path else script_dir / "replay.html"
    )
    if not html_path.is_file():
        raise FileNotFoundError(f"Replay HTML not found: {html_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run sync Playwright in a thread to avoid conflict with asyncio (Jupyter, Langfuse, etc.)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            _extract_keyframes_impl,
            events=events,
            keyframe_timestamps=keyframe_timestamps,
            output_dir=output_dir,
            html_path=html_path,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        return future.result()


def load_keyframe_images_as_base64(
    keyframe_paths: list[tuple[float, str]],
    max_size_kb: int = 500,
) -> list[tuple[float, str]]:
    """
    Load keyframe PNGs and return (time_s, base64_data_url) for embedding in prompts.
    Optionally skip or resize if over max_size_kb to control token cost.
    """
    out: list[tuple[float, str]] = []
    for time_s, path in keyframe_paths:
        try:
            with open(path, "rb") as f:
                raw = f.read()
            if max_size_kb > 0 and len(raw) > max_size_kb * 1024:
                # Skip or could resize with PIL here
                continue
            b64 = base64.standard_b64encode(raw).decode("ascii")
            out.append((time_s, f"data:image/png;base64,{b64}"))
        except Exception:
            continue
    return out
