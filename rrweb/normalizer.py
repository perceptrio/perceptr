"""
Transform rrweb raw events into normalized, idempotent, LLM-friendly events.

- Builds node map from FullSnapshot (type 2) so incremental events can resolve
  node ids to labels (e.g. "button \"Get started\"").
- Mouse move: emits where mouse ended up (x, y) for later frustration/pattern analysis.
- Mutation: updates node map from adds/removes so new elements resolve to labels.
- Scroll: includes scroll coordinates (x, y) for analysis.
- Deterministic: same events.json -> same normalized list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .node_map import (
    apply_node_to_map,
    build_node_maps,
    remove_from_map,
    resolve_node,
)


# Top-level rrweb event types
TYPE_FULL_SNAPSHOT = 2
TYPE_INCREMENTAL = 3
TYPE_META = 4
TYPE_CUSTOM = 5
TYPE_PLUGIN = 6
TYPE_NETWORK = 7  # custom event with method/url (network log)

# Incremental snapshot sources
SOURCE_MUTATION = 0
SOURCE_MOUSE_MOVE = 1
SOURCE_MOUSE_INTERACTION = 2
SOURCE_SCROLL = 3
SOURCE_VIEWPORT_RESIZE = 4
SOURCE_INPUT = 5

# Mouse interaction subtypes (for source 2)
MI_CLICK = 2
MI_FOCUS = 5
MI_BLUR = 6
MI_DBLCLICK = 4
MI_CONTEXT_MENU = 3

# Todo use settings from settings.py
RECORDING_INTERVAL_DURATION = 30


@dataclass
class NormalizedEvent:
    """One normalized, token-efficient event."""

    t: float  # seconds since session start
    e: str  # natural language, e.g. "user click on button \"Get started\""
    payload: dict | list | None = (
        None  # optional full payload for analysis (console, network, custom)
    )
    node_id: int | None = None
    node: dict | None = None
    interactive: bool | None = (
        None  # whether clicked element has triggers (href, role, onclick…)
    )

    def __init__(
        self,
        t: float,
        e: str,
        node_id: int | None = None,
        node: dict | None = None,
        payload: dict | list | None = None,
        interactive: bool | None = None,
    ):
        self.t = t
        self.e = e
        self.node_id = node_id
        self.node = node
        self.payload = payload
        self.interactive = interactive

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"t": self.t, "e": self.e}
        if self.payload is not None:
            out["payload"] = self.payload
        if self.interactive is not None:
            out["interactive"] = self.interactive
        return out


def _to_seconds(ts: int, start_ts: int) -> float:
    return round((ts - start_ts) / 1000.0, 2)


def _source_file_from_trace(trace: list[str]) -> str | None:
    """Extract source file from console trace (e.g. Hero.tsx:18:21). Handles URL-style lines."""
    if not trace:
        return None
    for line in trace[:3]:
        # URL-style: "http://.../Hero.tsx?t=123:18:21" -> "Hero.tsx:18:21"
        if ":" in line and (".tsx" in line or ".ts" in line or ".js" in line):
            basename = line.split("/")[-1] if "/" in line else line
            if "?" in basename:
                name_part = basename.split("?")[0]
            else:
                name_part = basename
            # End with :line:col?
            if basename.count(":") >= 2:
                before_line, line_no, col = basename.rsplit(":", 2)
                file_only = (
                    before_line.split("?")[0] if "?" in before_line else before_line
                )
                return f"{file_only}:{line_no}:{col}"
            if ".tsx" in name_part or ".ts" in name_part or ".js" in name_part:
                return name_part
    return None


def normalize_events(
    raw: dict[str, Any],
    *,
    skip_mouse_move: bool = False,
    skip_mutations: bool = False,
    collapse_scroll_ms: int | None = 800,
) -> list[NormalizedEvent]:
    """
    Convert raw rrweb session to a list of normalized, idempotent events.

    - skip_mouse_move: if True, do not emit mouse move (saves tokens). If False, emit where mouse ended up (x, y) for frustration/pattern analysis.
    - skip_mutations: if True, do not update node map from mutations. If False, apply adds/removes so new elements resolve to labels.
    - collapse_scroll_ms: merge scrolls within this window into one; use None to emit every scroll.
    """
    start_ts = raw.get("startTime", 0)
    events = raw.get("data", [])

    node_map: dict[int, str] = {}
    interactive_map: dict[int, bool] = {}
    out: list[NormalizedEvent] = []
    last_scroll_ts: int | None = None

    for ev in events:
        ev_type = ev.get("type")
        ts = ev.get("timestamp", 0)
        t_s = _to_seconds(ts, start_ts)
        data = ev.get("data") or {}

        if ev_type == TYPE_FULL_SNAPSHOT:
            root = data.get("node")
            if root:
                node_map, interactive_map = build_node_maps(root)
            continue

        if ev_type == TYPE_META:
            href = data.get("href")
            if href:
                if "#" in href:
                    section = href.split("#")[-1]
                    out.append(
                        NormalizedEvent(
                            t=t_s,
                            e=f"user navigated to #{section}",
                            node=data,
                            node_id=data.get("id"),
                        )
                    )
                else:
                    path = (
                        href.split("://")[-1].split("/", 1)[-1]
                        if "://" in href
                        else href
                    )
                    out.append(
                        NormalizedEvent(
                            t=t_s,
                            e=f"user navigated to {path or '/'}",
                            node=data,
                            node_id=data.get("id"),
                        )
                    )
            continue

        # Type 6: Plugin (e.g. console logs) – include payload for analysis
        if ev_type == TYPE_PLUGIN:
            data = ev.get("data") or {}
            plugin = data.get("plugin", "")
            payload_obj = data.get("payload") or {}
            if "console" in plugin:
                level = payload_obj.get("level", "log")
                msg_parts = payload_obj.get("payload", [])
                message = " ".join(str(p).strip('"') for p in msg_parts)
                trace = payload_obj.get("trace", [])
                source_file = _source_file_from_trace(trace)
                e_short = f"console [{level}]: {message[:80]}{'…' if len(message) > 80 else ''}"
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=e_short,
                        payload={
                            "level": level,
                            "payload": msg_parts,
                            "trace": trace,
                            "source_file": source_file,
                        },
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            else:
                e_short = f"plugin [{plugin}]: (see payload)"
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=e_short,
                        payload=data,
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            continue

        # Type 7: Network log – include method, url, status, body for analysis
        if ev_type == TYPE_NETWORK:
            method = ev.get("method", "GET")
            url = ev.get("url", "")
            status = ev.get("status")
            path_short = url.split("://")[-1].split("/", 1)[-1][:60] if url else ""
            e_short = f"network: {method} {path_short}" + (
                f" {status}" if status is not None else ""
            )
            net_payload: dict[str, Any] = {
                "method": method,
                "url": url,
                "status": status,
                "statusText": ev.get("statusText"),
                "duration": ev.get("duration"),
                "requestBody": ev.get("requestBody"),
                "responseBody": ev.get("responseBody"),
                "requestHeaders": ev.get("requestHeaders"),
                "responseHeaders": ev.get("responseHeaders"),
            }
            out.append(
                NormalizedEvent(
                    t=t_s,
                    e=e_short,
                    payload={k: v for k, v in net_payload.items() if v is not None},
                    node=data,
                    node_id=data.get("id"),
                )
            )
            continue

        # Type 5: Custom event – include full payload for analysis
        if ev_type == TYPE_CUSTOM:
            data = ev.get("data") or {}
            tag = data.get("tag", "custom")
            payload_custom = data.get("payload", data)
            e_short = f"custom [{tag}]: (see payload)"
            out.append(
                NormalizedEvent(
                    t=t_s,
                    e=e_short,
                    payload=payload_custom,
                    node=data,
                    node_id=data.get("id"),
                )
            )
            continue

        if ev_type != TYPE_INCREMENTAL:
            continue

        source = data.get("source")

        if source == SOURCE_MOUSE_MOVE:
            if not skip_mouse_move:
                positions = data.get("positions") or []
                if positions:
                    last = positions[-1]
                    x, y = last.get("x"), last.get("y")
                    node_id = last.get("id")
                    target = (
                        resolve_node(node_map, node_id) if node_id is not None else None
                    )
                    if x is not None and y is not None:
                        xi, yi = int(round(x)), int(round(y))
                        if target:
                            out.append(
                                NormalizedEvent(
                                    t=t_s,
                                    e=f"user moved mouse to ({xi}, {yi}) on {target}",
                                    node=data,
                                    node_id=data.get("id"),
                                )
                            )
                        else:
                            out.append(
                                NormalizedEvent(
                                    t=t_s,
                                    e=f"user moved mouse to ({xi}, {yi})",
                                    node=data,
                                    node_id=data.get("id"),
                                )
                            )
                    else:
                        out.append(
                            NormalizedEvent(
                                t=t_s,
                                e="user moved mouse",
                                node=data,
                                node_id=data.get("id"),
                            )
                        )
            continue

        if source == SOURCE_MUTATION:
            if not skip_mutations:
                for add in data.get("adds") or []:
                    node = add.get("node")
                    if node:
                        apply_node_to_map(node_map, node, interactive_map)
                removes = data.get("removes") or []
                ids_to_remove = []
                for r in removes:
                    if isinstance(r, dict) and "id" in r:
                        ids_to_remove.append(r["id"])
                    elif isinstance(r, int):
                        ids_to_remove.append(r)
                remove_from_map(node_map, ids_to_remove)
            continue

        if source == SOURCE_MOUSE_INTERACTION:
            mi_type = data.get("type")
            node_id = data.get("id")
            target = resolve_node(node_map, node_id)
            # Look up interactivity for click events
            is_interactive = (
                interactive_map.get(node_id) if node_id is not None else None
            )
            if mi_type == MI_CLICK:
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f"user click on {target}",
                        node=data,
                        node_id=data.get("id"),
                        interactive=is_interactive,
                    )
                )
            elif mi_type == MI_DBLCLICK:
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f"user double-click on {target}",
                        node=data,
                        node_id=data.get("id"),
                        interactive=is_interactive,
                    )
                )
            elif mi_type == MI_FOCUS:
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f"user focus on {target}",
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            elif mi_type == MI_BLUR:
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f"user blur {target}",
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            elif mi_type == MI_CONTEXT_MENU:
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f"user right-click on {target}",
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            # MouseDown/MouseUp omitted for token saving
            continue

        if source == SOURCE_SCROLL:
            if collapse_scroll_ms is not None and last_scroll_ts is not None:
                if ts - last_scroll_ts <= collapse_scroll_ms:
                    continue
            last_scroll_ts = ts
            x, y = data.get("x"), data.get("y")
            if x is not None and y is not None:
                xi, yi = int(round(x)), int(round(y))
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f"user scrolled through page (x={xi}, y={yi})",
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            else:
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e="user scrolled through page",
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            continue

        if source == SOURCE_VIEWPORT_RESIZE:
            w = data.get("width")
            h = data.get("height")
            if w is not None and h is not None:
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f"viewport resized to {w}x{h}",
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            continue

        if source == SOURCE_INPUT:
            node_id = data.get("id")
            target = resolve_node(node_map, node_id)
            text = data.get("text", "")
            if text:
                # Truncate long values for tokens
                preview = (text[:40] + "…") if len(text) > 40 else text
                out.append(
                    NormalizedEvent(
                        t=t_s,
                        e=f'user typed in {target}: "{preview}"',
                        node=data,
                        node_id=data.get("id"),
                    )
                )
            else:
                # checkbox/radio etc
                checked = data.get("isChecked")
                if checked is not None:
                    out.append(
                        NormalizedEvent(
                            t=t_s,
                            e=f"user set {target} to {'checked' if checked else 'unchecked'}",
                            node=data,
                            node_id=data.get("id"),
                        )
                    )
                else:
                    out.append(
                        NormalizedEvent(
                            t=t_s,
                            e=f"user input on {target}",
                            node=data,
                            node_id=data.get("id"),
                        )
                    )
            continue

    return out


def normalized_events_to_dict_list(
    normalized: list[NormalizedEvent],
) -> list[dict[str, Any]]:
    """For JSON serialization / LLM context."""
    return [e.to_dict() for e in normalized]
