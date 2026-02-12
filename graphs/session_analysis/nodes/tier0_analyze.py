"""
Programmatic heuristic analysis from normalized events (no AI).

Detects: rage clicks, dead clicks, navigation loops, form struggles, scroll thrashing.
Computes: health score, confidence score, overall user behavior.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any
from common.schemas.session_analysis import (
    Issue,
    KeyEvent,
    SessionAnalysisResult,
    TimestampInterval,
)
from common.types import (
    CATEGORY_BUG,
    CATEGORY_ENHANCEMENT,
    CATEGORY_PERFORMANCE_ISSUE,
    CATEGORY_USABILITY_ISSUE,
    SIGNAL_DEAD_CLICK,
    SIGNAL_FORM_STRUGGLE,
    SIGNAL_NAVIGATION_LOOP,
    SIGNAL_RAGE_CLICK,
    SIGNAL_SCROLL_THRASHING,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)
from graphs.session_analysis.state import SessionAnalysisState
from rrweb.compressor import compress_events

# Regex: [3s], [8-10s], [8–10s]
_TS_RE = re.compile(r"^\[(\d+)(?:[–\-](\d+))?s\]")


@dataclass
class _ParsedBuckets:
    """Structured events parsed from normalized event strings."""

    clicks: list[dict[str, Any]] = field(default_factory=list)  # {t, target}
    scrolls: list[dict[str, Any]] = field(default_factory=list)  # {t, x, y}
    navigations: list[dict[str, Any]] = field(default_factory=list)  # {t, url}
    inputs: list[dict[str, Any]] = field(default_factory=list)  # {t, target, value?}
    network: list[dict[str, Any]] = field(
        default_factory=list
    )  # {t, method, url, status?}
    console: list[dict[str, Any]] = field(default_factory=list)  # {t, level}


# Regex for scroll coords: "user scrolled through page (x=0, y=1924)" or "(x=0, y=1924.44)"
_SCROLL_COORDS_RE = re.compile(r"\(x=([-\d]+),\s*y=([-\d.]+)\)")


def _parse_normalized_events(events: list[dict[str, Any]]) -> _ParsedBuckets:
    """Parse normalized event list (t, e, payload?) into typed buckets."""
    buckets = _ParsedBuckets()
    for ev in events:
        t = ev.get("t", 0.0)
        e = ev.get("e", "")
        payload = ev.get("payload")

        if e.startswith("user click on "):
            target = e[len("user click on ") :].strip()
            buckets.clicks.append({"t": t, "target": target})

        elif "user scrolled through page" in e:
            m = _SCROLL_COORDS_RE.search(e)
            if m:
                x, y = int(m.group(1)), float(m.group(2))
                buckets.scrolls.append({"t": t, "x": x, "y": y})
            else:
                buckets.scrolls.append({"t": t, "x": None, "y": None})

        elif e.startswith("user navigated to "):
            url = e[len("user navigated to ") :].strip()
            buckets.navigations.append({"t": t, "url": url})

        elif e.startswith("user typed in "):
            # "user typed in button \"X\": \"value\"" or "user typed in input \"Y\": \"val\""
            rest = e[len("user typed in ") :].strip()
            if ': "' in rest:
                target_part, value_part = rest.split(': "', 1)
                target = target_part.strip()
                value = (
                    value_part.rstrip('"').strip()
                    if value_part.endswith('"')
                    else value_part
                )
            else:
                target = rest
                value = None
            buckets.inputs.append({"t": t, "target": target, "value": value})

        elif e.startswith("user set ") and " to " in e:
            # "user set input \"X\" to checked"
            rest = e[len("user set ") :].strip()
            if " to " in rest:
                target_part, _ = rest.split(" to ", 1)
                target = target_part.strip()
            else:
                target = rest
            buckets.inputs.append({"t": t, "target": target, "value": None})

        elif e.startswith("network:"):
            # payload may have method, url, status
            method = "GET"
            url = ""
            status = None
            if isinstance(payload, dict):
                method = payload.get("method", method)
                url = payload.get("url", url)
                status = payload.get("status")
            buckets.network.append(
                {"t": t, "method": method, "url": url, "status": status}
            )

        elif e.startswith("console ["):
            # "console [log]: msg" or "console [error]: msg"
            level = "log"
            if "]: " in e:
                level = e.split("[", 1)[1].split("]", 1)[0].strip()
            buckets.console.append({"t": t, "level": level})
    return buckets


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------


@dataclass
class AnalyzeConfig:
    rage_click_window_s: float = 2.0
    rage_click_min_count: int = 3
    dead_click_effect_window_s: float = 1.0
    form_struggle_min_inputs: int = 3
    navigation_loop_min_visits: int = 3
    scroll_thrash_window_s: float = 3.0
    scroll_thrash_min_direction_changes: int = 4


# -----------------------------------------------------------------------------
# Heuristics
# -----------------------------------------------------------------------------


def _detect_rage_clicks(buckets: _ParsedBuckets, config: AnalyzeConfig) -> list[Issue]:
    """Rapid repeated clicks on same target within window."""
    issues: list[Issue] = []
    clicks = sorted(buckets.clicks, key=lambda x: x["t"])
    if len(clicks) < config.rage_click_min_count:
        return issues
    window_s = config.rage_click_window_s
    i = 0
    while i < len(clicks):
        group = [clicks[i]]
        j = i + 1
        while j < len(clicks):
            if (
                clicks[j]["t"] - clicks[i]["t"] <= window_s
                and clicks[j]["target"] == clicks[i]["target"]
            ):
                group.append(clicks[j])
                j += 1
            else:
                break
        if len(group) >= config.rage_click_min_count:
            count = len(group)
            target = group[0]["target"]
            t0 = group[0]["t"]
            duration = group[-1]["t"] - t0
            severity = (
                SEVERITY_CRITICAL
                if count >= 6
                else (SEVERITY_HIGH if count >= 4 else SEVERITY_MEDIUM)
            )
            issues.append(
                Issue(
                    type=SIGNAL_RAGE_CLICK,
                    frequency=count,
                    timestamp=_seconds_to_mmss(t0),
                    severity=severity,
                    root_cause=f"User clicked {target} {count} times in {duration:.1f}s with no response",
                    reproduction_steps=f"Click on {target or 'element'} rapidly {count} times",
                    target=target,
                    category=(
                        CATEGORY_USABILITY_ISSUE
                        if severity in (SEVERITY_MEDIUM, SEVERITY_LOW)
                        else CATEGORY_BUG
                    ),
                )
            )
            i = j
        else:
            i += 1
    return issues


def _detect_dead_clicks(buckets: _ParsedBuckets, config: AnalyzeConfig) -> list[Issue]:
    """Clicks after which no navigation, network, scroll, or meaningful input within window."""
    issues: list[Issue] = []
    window_s = config.dead_click_effect_window_s
    for click in buckets.clicks:
        t0 = click["t"]
        target = click["target"]
        has_effect = False
        for nav in buckets.navigations:
            if nav["t"] > t0 and nav["t"] <= t0 + window_s:
                has_effect = True
                break
        if not has_effect:
            for net in buckets.network:
                if net["t"] > t0 and net["t"] <= t0 + window_s:
                    has_effect = True
                    break
        if not has_effect and len(buckets.scrolls) >= 2:
            scroll_ys = [
                s
                for s in buckets.scrolls
                if s.get("y") is not None and s["t"] > t0 and s["t"] <= t0 + window_s
            ]
            before_ys = [
                s["y"]
                for s in buckets.scrolls
                if s.get("y") is not None and s["t"] <= t0
            ]
            if scroll_ys and before_ys and abs(scroll_ys[0]["y"] - before_ys[-1]) > 100:
                has_effect = True
        if not has_effect:
            for inp in buckets.inputs:
                if inp["t"] > t0 and inp["t"] <= t0 + window_s:
                    has_effect = True
                    break

        if not has_effect:
            # Optimize: Use a dict for O(1) lookups by description
            if not hasattr(_detect_dead_clicks, "_desc_issue_map"):
                _detect_dead_clicks._desc_issue_map = {}
            desc_issue_map = _detect_dead_clicks._desc_issue_map
            desc = f"Click on {target} had no visible effect"
            if desc not in desc_issue_map:
                issue = Issue(
                    type=SIGNAL_DEAD_CLICK,
                    severity=SEVERITY_LOW,
                    root_cause=desc,
                    reproduction_steps=f"Click on {target or 'element'} and observe no response",
                    target=target,
                    timestamp=_seconds_to_mmss(t0),
                    frequency=1,
                    category=CATEGORY_USABILITY_ISSUE,
                )
                issues.append(issue)
                desc_issue_map[desc] = issue
            else:
                desc_issue_map[desc].frequency += 1
    return issues


def _detect_navigation_loops(
    buckets: _ParsedBuckets, config: AnalyzeConfig
) -> list[Issue]:
    """Same URL/section visited repeatedly."""
    issues: list[Issue] = []
    if len(buckets.navigations) < config.navigation_loop_min_visits:
        return issues
    by_url: dict[str, list[dict]] = {}
    for nav in buckets.navigations:
        url = (nav["url"] or "").split("?")[0]
        by_url.setdefault(url, []).append(nav)
    for url, visits in by_url.items():
        if len(visits) >= config.navigation_loop_min_visits:
            t0 = visits[0]["t"]
            short = url.replace("http://", "").replace("https://", "").strip("/") or url
            severity = SEVERITY_HIGH if len(visits) >= 5 else SEVERITY_MEDIUM
            issues.append(
                Issue(
                    type=SIGNAL_NAVIGATION_LOOP,
                    timestamp=_seconds_to_mmss(t0),
                    severity=severity,
                    root_cause=f"User visited {short} {len(visits)} times (possible confusion)",
                    reproduction_steps=f"Navigate to {url or 'page'} multiple times",
                    target=url,
                    frequency=len(visits),
                    category=CATEGORY_USABILITY_ISSUE,
                )
            )
    return issues


def _detect_form_struggles(
    buckets: _ParsedBuckets, config: AnalyzeConfig
) -> list[Issue]:
    """Repeated inputs on same field (corrections / struggle)."""
    issues: list[Issue] = []
    by_target: dict[str, list[dict]] = {}
    for inp in buckets.inputs:
        target = inp.get("target") or "unknown"
        by_target.setdefault(target, []).append(inp)
    for target, inputs in by_target.items():
        if len(inputs) >= config.form_struggle_min_inputs:
            t0 = sorted(inputs, key=lambda x: x["t"])[0]["t"]
            severity = SEVERITY_HIGH if len(inputs) >= 5 else SEVERITY_MEDIUM
            issues.append(
                Issue(
                    type=SIGNAL_FORM_STRUGGLE,
                    timestamp=_seconds_to_mmss(t0),
                    severity=severity,
                    root_cause=f"User struggled with {target} ({len(inputs)} inputs / corrections)",
                    reproduction_steps=f"Attempt to fill {target or 'form field'} with corrections",
                    target=target,
                    frequency=len(inputs),
                    category=CATEGORY_USABILITY_ISSUE,
                )
            )
    return issues


def _detect_scroll_thrashing(
    buckets: _ParsedBuckets, config: AnalyzeConfig
) -> list[Issue]:
    """Rapid up/down scroll direction changes in a short window."""
    issues: list[Issue] = []
    scrolls = sorted(
        [s for s in buckets.scrolls if s.get("y") is not None], key=lambda x: x["t"]
    )
    if len(scrolls) < 3:
        return issues
    window_s = config.scroll_thrash_window_s
    i = 0
    while i < len(scrolls) - 1:
        group_start = scrolls[i]
        direction_changes = 0
        prev_direction = None
        j = i
        while j < len(scrolls) - 1:
            if scrolls[j]["t"] - group_start["t"] > window_s:
                break
            y_diff = scrolls[j + 1]["y"] - scrolls[j]["y"]
            if y_diff != 0:
                direction = "down" if y_diff > 0 else "up"
                if prev_direction and direction != prev_direction:
                    direction_changes += 1
                prev_direction = direction
            j += 1
        if direction_changes >= config.scroll_thrash_min_direction_changes:
            severity = SEVERITY_HIGH if direction_changes >= 6 else SEVERITY_MEDIUM
            issues.append(
                Issue(
                    type=SIGNAL_SCROLL_THRASHING,
                    timestamp=_seconds_to_mmss(group_start["t"]),
                    severity=severity,
                    root_cause=f"Rapid scrolling up/down ({direction_changes} direction changes) - user may be searching",
                    reproduction_steps="Scroll up and down rapidly looking for content",
                    frequency=direction_changes,
                    category=(
                        CATEGORY_USABILITY_ISSUE
                        if severity in (SEVERITY_MEDIUM, SEVERITY_LOW)
                        else CATEGORY_BUG
                    ),
                )
            )
            i = j
        else:
            i += 1
    return issues


def _health_score(issues: list[Issue]) -> float:
    """0-100; higher = healthier. Penalize by issue type and severity; floor 5."""
    penalty = 0.0
    for s in issues:
        w = {
            "rage_click": 12,
            "dead_click": 4,
            "navigation_loop": 10,
            "form_struggle": 8,
            "scroll_thrashing": 5,
        }.get(s.type, 5)
        sev_w = {
            SEVERITY_CRITICAL: 1.5,
            SEVERITY_HIGH: 1.2,
            SEVERITY_MEDIUM: 1.0,
            SEVERITY_LOW: 0.5,
        }.get(s.severity, 1.0)
        penalty += w * sev_w
    return max(5.0, min(100.0, 100.0 - penalty))


def _confidence_score(events_count: int, issues_count: int) -> float:
    """0-1; more events and some issues = higher confidence."""
    if events_count < 5:
        return 0.3
    base = 0.4 + min(0.4, events_count / 500.0)
    if issues_count > 0:
        base = min(1.0, base + 0.2)
    return round(min(1.0, base), 2)


def _seconds_to_mmss(seconds: float) -> str:
    """Convert seconds (float) to MM:SS format."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _timestamp_to_seconds(timestamp: str) -> float:
    """Convert MM:SS timestamp to seconds."""
    minutes, seconds = map(int, timestamp.split(":"))
    return minutes * 60 + seconds


def _create_intervals(
    events: list[dict[str, Any]], all_issues: list[Issue], buckets: _ParsedBuckets
) -> list[TimestampInterval]:
    """Group events into logical intervals and create timestamp descriptions."""
    if not events:
        return []

    intervals: list[TimestampInterval] = []

    # Simple strategy: group by major action clusters (clicks, form fills, navigation)
    # Or create one interval per 30s chunk, or per logical task
    # For now: create intervals based on navigation events and major action clusters

    # Strategy: Create intervals around navigations and form submissions
    interval_starts: list[float] = [events[0]["t"]]
    for nav in buckets.navigations:
        interval_starts.append(nav["t"])
    # Add form completion points (after multiple inputs)
    input_times = sorted([inp["t"] for inp in buckets.inputs])
    if len(input_times) >= 3:
        # Group inputs into clusters (gaps > 5s = new cluster)
        cluster_start = input_times[0]
        for i in range(1, len(input_times)):
            if input_times[i] - input_times[i - 1] > 5.0:
                interval_starts.append(cluster_start)
                cluster_start = input_times[i]
        interval_starts.append(cluster_start)

    interval_starts = sorted(set[float](interval_starts))
    if events[-1]["t"] not in interval_starts:
        interval_starts.append(events[-1]["t"])

    # Create intervals
    for i in range(len(interval_starts) - 1):
        start_t = interval_starts[i]
        end_t = interval_starts[i + 1]

        # Events in this interval
        interval_events = [e for e in events if start_t <= e["t"] < end_t]
        if not interval_events:
            continue

        # Issues in this interval (filter by timestamp)
        interval_issues = [
            s
            for s in all_issues
            if start_t <= _timestamp_to_seconds(s.timestamp) < end_t
        ]

        # Key events: 3-5 most significant events in this interval (timestamp + description)
        key_events: list[KeyEvent] = []
        # Filter to significant events (clicks, navigations, inputs, network)
        significant = [
            ev
            for ev in interval_events
            if any(
                kw in ev.get("e", "")
                for kw in ["click", "navigated", "typed", "network:", "console [error]"]
            )
        ]
        if not significant:
            # No significant events, use randomly pick 3 events as key events
            significant = random.sample(interval_events, min(3, len(interval_events)))
        # Take up to 5 significant events
        for ev in significant[:5]:
            key_events.append(
                KeyEvent(
                    timestamp=_seconds_to_mmss(ev["t"]),
                    description=ev.get("e", "Event")[:150],
                )
            )

        # Short title from first major action
        title = "Session activity"
        if interval_events:
            first_e = interval_events[0].get("e", "")
            if "navigated" in first_e:
                title = "Navigation"
            elif "click" in first_e:
                title = "Interaction"
            elif "typed" in first_e or "input" in first_e:
                title = "Form input"
            elif "scrolled" in first_e:
                title = "Browsing"

        # Description: summarize actions in interval
        desc_parts = []
        clicks_in_interval = sum(
            1 for e in interval_events if "click" in e.get("e", "")
        )
        navs_in_interval = sum(
            1 for e in interval_events if "navigated" in e.get("e", "")
        )
        inputs_in_interval = sum(
            1
            for e in interval_events
            if "typed" in e.get("e", "") or "input" in e.get("e", "")
        )
        scrolls_in_interval = sum(
            1 for e in interval_events if "scrolled" in e.get("e", "")
        )
        if clicks_in_interval:
            desc_parts.append(f"{clicks_in_interval} click(s)")
        if navs_in_interval:
            desc_parts.append(f"{navs_in_interval} navigation(s)")
        if inputs_in_interval:
            desc_parts.append(f"{inputs_in_interval} input(s)")
        if scrolls_in_interval:
            desc_parts.append(f"{scrolls_in_interval} scroll(s)")

        intervals.append(
            TimestampInterval(
                start_time=_seconds_to_mmss(start_t),
                end_time=_seconds_to_mmss(end_t),
                short_title=title,
                issues=interval_issues,
                key_events=key_events,
            )
        )

    return intervals


def _generate_summary(
    buckets: _ParsedBuckets, issues: list[Issue], duration_s: float
) -> str:
    """Generate overall summary matching video analyzer format."""
    parts = []
    parts.append(f"Session duration: {int(duration_s)}s.")

    # Key actions
    action_parts = []
    if buckets.clicks:
        action_parts.append(f"{len(buckets.clicks)} clicks")
    if buckets.navigations:
        action_parts.append(f"{len(buckets.navigations)} navigations")
    if buckets.inputs:
        action_parts.append(f"{len(buckets.inputs)} form inputs")
    if buckets.scrolls:
        action_parts.append(f"{len(buckets.scrolls)} scrolls")
    if action_parts:
        parts.append(f"User performed: {', '.join(action_parts)}.")

    # Issues summary
    if issues:
        issue_counts = {}
        for s in issues:
            issue_counts[s.type] = issue_counts.get(s.type, 0) + 1
        issue_parts = []
        for sig_type, count in issue_counts.items():
            issue_parts.append(f"{count} {sig_type.replace('_', ' ')}")
        parts.append(f"Issues: {', '.join(issue_parts)}.")
    else:
        parts.append("No significant UX issues detected.")

    return " ".join(parts)


def _generate_title(buckets: _ParsedBuckets) -> str:
    """Generate title from session actions."""
    if buckets.navigations:
        # Use first navigation as hint
        first_nav = buckets.navigations[0].get("url", "")
        if "#" in first_nav:
            section = first_nav.split("#")[-1]
            return f"Session: {section.replace('-', ' ').title()}"
        return "User session"
    if buckets.inputs:
        return "Form completion session"
    if buckets.clicks:
        return "Interactive session"
    return "User session recording"


def _extract_user_actions(buckets: _ParsedBuckets, issues: list[Issue]) -> list[str]:
    """Derive user action tags from detected issues and event buckets.

    Returns a list of short tags like ["frustrated", "confused", "form_filling", ...]
    (max 8 tags).
    """
    tags: list[str] = []

    # --- Issue-based tags ---
    rage = sum(1 for s in issues if s.type == SIGNAL_RAGE_CLICK)
    dead = sum(1 for s in issues if s.type == SIGNAL_DEAD_CLICK)
    nav_loop = sum(1 for s in issues if s.type == SIGNAL_NAVIGATION_LOOP)
    form_struggle = sum(1 for s in issues if s.type == SIGNAL_FORM_STRUGGLE)
    scroll_thrash = sum(1 for s in issues if s.type == SIGNAL_SCROLL_THRASHING)

    if rage:
        tags.append("frustrated")
    if dead >= 3:
        tags.append("stuck")
    elif dead:
        tags.append("clicking_without_response")
    if nav_loop:
        tags.append("confused")
    if form_struggle:
        tags.append("struggling_with_form")
    if scroll_thrash:
        tags.append("searching")

    # --- Activity-based tags ---
    if buckets.inputs:
        tags.append("form_filling")
    if len(buckets.navigations) >= 4:
        tags.append("exploring")
    elif buckets.navigations:
        tags.append("navigating")
    if buckets.scrolls and not scroll_thrash:
        tags.append("browsing")

    # --- Severity-based emotional tags ---
    critical = sum(1 for s in issues if s.severity == SEVERITY_CRITICAL)
    high = sum(1 for s in issues if s.severity == SEVERITY_HIGH)
    if critical:
        tags.append("blocked")
    elif high >= 2:
        tags.append("hesitant")

    # Deduplicate and cap at 8
    seen: set[str] = set()
    unique: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique.append(tag)
    return unique[:8]


def analyze_events(
    normalized_events: list[dict[str, Any]] | list[Any],
    config: AnalyzeConfig | None = None,
) -> SessionAnalysisResult:
    """
    Run programmatic heuristics on normalized events (no AI).

    normalized_events: list of {"t": float, "e": str, "payload": ...} from normalizer,
    or list of NormalizedEvent (will be converted via to_dict()).
    """
    events = normalized_events
    if events and hasattr(events[0], "to_dict"):
        events = [x.to_dict() for x in events]
    cfg = config or AnalyzeConfig()
    buckets = _parse_normalized_events(events)
    issues: list[Issue] = []
    issues.extend(_detect_rage_clicks(buckets, cfg))
    issues.extend(_detect_dead_clicks(buckets, cfg))
    issues.extend(_detect_navigation_loops(buckets, cfg))
    issues.extend(_detect_form_struggles(buckets, cfg))
    issues.extend(_detect_scroll_thrashing(buckets, cfg))
    issues.sort(key=lambda x: _timestamp_to_seconds(x.timestamp))

    health = _health_score(issues)
    confidence = _confidence_score(len(events), len(issues))
    actions = _extract_user_actions(buckets, issues)

    # Generate intervals, summary, title
    duration_s = events[-1]["t"] - events[0]["t"] if len(events) > 1 else 0
    intervals = _create_intervals(events, issues, buckets)
    summary = _generate_summary(buckets, issues, duration_s)
    title = _generate_title(buckets)

    return SessionAnalysisResult(
        health_score=round(health, 1),
        confidence_score=confidence,
        user_actions=actions,
        intervals=intervals,
        summary=summary,
        title=title,
    )


def _mmss_to_seconds(mmss: str) -> float:
    """Convert MM:SS to seconds."""
    parts = mmss.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _enrich_intervals_with_compressed(
    intervals: list[TimestampInterval], compressed_events: str
) -> list[TimestampInterval]:
    """Replace verbose key_events with cleaner compressed event lines.

    Compressed events are more readable and token-efficient than raw
    normalised event strings. Each line is assigned to the interval whose
    time range contains it, as KeyEvent(timestamp=MM:SS, description=text).
    """
    # Parse lines with their approximate second offset
    entries: list[tuple[int, str]] = []
    for line in compressed_events.strip().splitlines():
        stripped = line.strip()
        m = _TS_RE.match(stripped)
        if m:
            t = int(m.group(1))
            entries.append((t, stripped))
        elif stripped.startswith("[!") and entries:
            # Issue marker — belongs to same timestamp as previous entry
            entries.append((entries[-1][0], stripped))

    updated = []
    for interval in intervals:
        start_s = _mmss_to_seconds(interval.start_time)
        end_s = _mmss_to_seconds(interval.end_time)
        matched = [
            KeyEvent(timestamp=_seconds_to_mmss(t), description=text)
            for t, text in entries
            if start_s <= t < end_s
        ]
        if matched:
            updated.append(interval.model_copy(update={"key_events": matched[:10]}))
        else:
            updated.append(interval)
    return updated


def tier0_analyze_node(state: SessionAnalysisState) -> dict:
    """Run all programmatic detectors and produce a baseline result.

    Reads:  normalized_events
    Writes: prog_result  (SessionAnalysisResult)
            compressed_events  (str)
    """
    events = state["normalized_events"]
    prog_result = analyze_events(events)
    compressed = compress_events(events, prog_result)

    if compressed and prog_result.intervals:
        enriched = _enrich_intervals_with_compressed(prog_result.intervals, compressed)
        result = prog_result.model_copy(update={"intervals": enriched})
    else:
        result = prog_result
    return {"prog_result": result, "compressed_events": compressed}
