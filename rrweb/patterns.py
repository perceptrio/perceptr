"""
Behavioral pattern extraction from normalized events.

Extracts high-level behavioral issues that indicate user intent,
confusion, or engagement patterns. Used to provide context to LLM
without sending every event.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class BehavioralPattern:
    """A detected behavioral pattern in the session."""

    type: str  # search_behavior, hesitation, navigation_confusion, linear_browsing, quick_bounce, form_abandonment
    description: str
    time_range: Optional[Tuple[float, float]] = None  # (start_s, end_s)
    severity: str = "info"  # info, warning

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "description": self.description,
            "time_range": list(self.time_range) if self.time_range else None,
            "severity": self.severity,
        }


def _extract_scroll_y(event: dict) -> Optional[float]:
    """Extract y scroll position from event."""
    e = event.get("e", "")
    match = re.search(r"y=(-?[\d.]+)", e)
    if match:
        return float(match.group(1))
    return None


def _extract_url(event: dict) -> Optional[str]:
    """Extract URL from navigation event."""
    e = event.get("e", "")
    if "navigated to " in e:
        return e.split("navigated to ", 1)[1].strip()
    return None


def _detect_search_behavior(events: List[dict]) -> List[BehavioralPattern]:
    """
    Detect scroll search behavior (user scrolling up/down looking for something).

    Triggered when there are > 5 direction changes in scrolling.
    """
    patterns = []

    scroll_events = [
        (e.get("t", 0), _extract_scroll_y(e))
        for e in events
        if "scrolled" in e.get("e", "")
    ]
    scroll_events = [(t, y) for t, y in scroll_events if y is not None]

    if len(scroll_events) < 4:
        return patterns

    # Find clusters of scroll thrashing
    window_size = 10  # seconds
    i = 0
    while i < len(scroll_events):
        window_start = scroll_events[i][0]
        window_end = window_start + window_size

        # Get scrolls in this window
        window_scrolls = [
            (t, y) for t, y in scroll_events if window_start <= t <= window_end
        ]

        if len(window_scrolls) >= 4:
            # Count direction changes
            direction_changes = 0
            for j in range(2, len(window_scrolls)):
                prev_dir = window_scrolls[j - 1][1] - window_scrolls[j - 2][1]
                curr_dir = window_scrolls[j][1] - window_scrolls[j - 1][1]
                if prev_dir * curr_dir < 0:
                    direction_changes += 1

            if direction_changes >= 3:
                patterns.append(
                    BehavioralPattern(
                        type="search_behavior",
                        description=f"User scrolled up/down {direction_changes} times, suggesting they were searching for something",
                        time_range=(window_start, window_scrolls[-1][0]),
                        severity="warning",
                    )
                )
                # Skip past this cluster
                i = next(
                    (idx for idx, (t, _) in enumerate(scroll_events) if t > window_end),
                    len(scroll_events),
                )
                continue

        i += 1

    return patterns


def _detect_navigation_confusion(events: List[dict]) -> List[BehavioralPattern]:
    """
    Detect navigation confusion (visiting same URL 3+ times).
    """
    patterns = []

    nav_events = [
        (e.get("t", 0), _extract_url(e))
        for e in events
        if "navigated to" in e.get("e", "")
    ]
    nav_events = [(t, url) for t, url in nav_events if url]

    # Count visits per URL (normalize by removing query params)
    url_visits: dict[str, List[float]] = {}
    for t, url in nav_events:
        # Normalize URL
        base_url = url.split("?")[0].split("#")[0] if url else url
        if base_url not in url_visits:
            url_visits[base_url] = []
        url_visits[base_url].append(t)

    for url, times in url_visits.items():
        if len(times) >= 3:
            patterns.append(
                BehavioralPattern(
                    type="navigation_confusion",
                    description=f"User visited '{url}' {len(times)} times - possible difficulty finding information",
                    time_range=(min(times), max(times)),
                    severity="warning",
                )
            )

    return patterns


def _detect_hesitation(events: List[dict]) -> List[BehavioralPattern]:
    """
    Detect hesitation (5-30s pause between meaningful actions).
    """
    patterns = []

    # Filter to meaningful events (not mouse moves or scrolls)
    meaningful = [
        e
        for e in events
        if any(
            kw in e.get("e", "") for kw in ["click", "typed", "navigated", "network:"]
        )
    ]

    if len(meaningful) < 2:
        return patterns

    for i in range(1, len(meaningful)):
        gap = meaningful[i].get("t", 0) - meaningful[i - 1].get("t", 0)

        if 5 < gap < 30:
            prev_event = meaningful[i - 1].get("e", "")[:50]
            patterns.append(
                BehavioralPattern(
                    type="hesitation",
                    description=f"User paused for {gap:.0f}s after: {prev_event}",
                    time_range=(
                        meaningful[i - 1].get("t", 0),
                        meaningful[i].get("t", 0),
                    ),
                    severity="info",
                )
            )

    return patterns


def _detect_linear_browsing(events: List[dict]) -> List[BehavioralPattern]:
    """
    Detect linear browsing (smooth scroll through content with few interactions).
    """
    patterns = []

    scroll_events = [e for e in events if "scrolled" in e.get("e", "")]
    click_events = [e for e in events if "click" in e.get("e", "")]

    if len(scroll_events) > 10 and len(click_events) < 3:
        # Check if scrolling is mostly in one direction
        y_values = [_extract_scroll_y(e) for e in scroll_events]
        y_values = [y for y in y_values if y is not None]

        if len(y_values) > 2:
            direction_changes = sum(
                1
                for i in range(2, len(y_values))
                if (y_values[i - 1] - y_values[i - 2]) * (y_values[i] - y_values[i - 1])
                < 0
            )

            if direction_changes < 3:
                patterns.append(
                    BehavioralPattern(
                        type="linear_browsing",
                        description="User scrolled through content linearly with few interactions - reading/scanning",
                        time_range=(
                            scroll_events[0].get("t", 0),
                            scroll_events[-1].get("t", 0),
                        ),
                        severity="info",
                    )
                )

    return patterns


def _detect_quick_bounce(
    events: List[dict], session_duration: float
) -> List[BehavioralPattern]:
    """
    Detect quick bounce (< 15s session on landing page with no meaningful interaction).
    """
    patterns = []

    if session_duration > 15:
        return patterns

    # Check for meaningful interactions
    meaningful = [
        e
        for e in events
        if any(
            kw in e.get("e", "")
            for kw in ["click on button", "typed in", "network: POST"]
        )
    ]

    if len(meaningful) == 0:
        patterns.append(
            BehavioralPattern(
                type="quick_bounce",
                description=f"User left after {session_duration:.0f}s with no meaningful interaction - possible UI/content issue",
                time_range=(0, session_duration),
                severity="warning",
            )
        )

    return patterns


def _detect_form_abandonment(events: List[dict]) -> List[BehavioralPattern]:
    """
    Detect form abandonment (started filling form but didn't submit).
    """
    patterns = []

    form_events = [
        e for e in events if "typed in" in e.get("e", "") or "set " in e.get("e", "")
    ]
    submit_events = [
        e
        for e in events
        if "click on button" in e.get("e", "")
        and any(
            kw in e.get("e", "").lower()
            for kw in ["submit", "send", "join", "sign", "register", "continue", "next"]
        )
    ]
    network_posts = [
        e for e in events if "network:" in e.get("e", "") and "POST" in e.get("e", "")
    ]

    if len(form_events) >= 2 and len(submit_events) == 0 and len(network_posts) == 0:
        # User filled form but never submitted
        patterns.append(
            BehavioralPattern(
                type="form_abandonment",
                description=f"User filled {len(form_events)} form fields but never submitted",
                time_range=(form_events[0].get("t", 0), form_events[-1].get("t", 0)),
                severity="warning",
            )
        )

    return patterns


def _detect_rage_clicking_context(events: List[dict]) -> List[BehavioralPattern]:
    """
    Add context about what happened before/after rage clicks.
    """
    patterns = []

    # Find rapid click sequences
    click_events = [(e.get("t", 0), e) for e in events if "click on" in e.get("e", "")]

    if len(click_events) < 3:
        return patterns

    i = 0
    while i < len(click_events) - 2:
        # Check for 3+ clicks within 2 seconds
        window_clicks = [click_events[i]]
        j = i + 1
        while j < len(click_events) and click_events[j][0] - click_events[i][0] < 2:
            window_clicks.append(click_events[j])
            j += 1

        if len(window_clicks) >= 3:
            # Check if same target
            targets = [e.get("e", "") for _, e in window_clicks]
            if len(set(targets)) == 1:
                # Look for what happened after
                after_time = window_clicks[-1][0]
                after_events = [
                    e
                    for e in events
                    if e.get("t", 0) > after_time and e.get("t", 0) < after_time + 5
                ]

                context = ""
                if any("navigated" in e.get("e", "") for e in after_events):
                    context = "User navigated away after clicking"
                elif any("network:" in e.get("e", "") for e in after_events):
                    context = "Network request occurred after clicking"
                elif not after_events:
                    context = "Nothing happened after rapid clicking"

                if context:
                    patterns.append(
                        BehavioralPattern(
                            type="rage_click_context",
                            description=context,
                            time_range=(window_clicks[0][0], window_clicks[-1][0]),
                            severity="info",
                        )
                    )

            i = j
        else:
            i += 1

    return patterns


def extract_patterns(
    normalized_events: List[dict],
    session_duration: Optional[float] = None,
) -> List[BehavioralPattern]:
    """
    Extract all behavioral patterns from normalized events.

    Args:
        normalized_events: List of normalized event dicts with 't' and 'e' keys
        session_duration: Optional session duration in seconds (calculated if not provided)

    Returns:
        List of detected behavioral patterns
    """
    # Convert if needed
    events = normalized_events
    if events and hasattr(events[0], "to_dict"):
        events = [e.to_dict() for e in events]

    if not events:
        return []

    # Calculate duration if not provided
    if session_duration is None:
        times = [e.get("t", 0) for e in events]
        session_duration = max(times) - min(times) if times else 0

    patterns: List[BehavioralPattern] = []

    # Run all pattern detectors
    patterns.extend(_detect_search_behavior(events))
    patterns.extend(_detect_navigation_confusion(events))
    patterns.extend(_detect_hesitation(events))
    patterns.extend(_detect_linear_browsing(events))
    patterns.extend(_detect_quick_bounce(events, session_duration))
    patterns.extend(_detect_form_abandonment(events))
    patterns.extend(_detect_rage_clicking_context(events))

    # Sort by time
    patterns.sort(key=lambda p: p.time_range[0] if p.time_range else 0)

    return patterns


def patterns_to_text(patterns: List[BehavioralPattern]) -> str:
    """Convert patterns to text for LLM context."""
    if not patterns:
        return "No significant behavioral patterns detected."

    lines = ["Behavioral Context:"]
    for p in patterns:
        severity_marker = "[!]" if p.severity == "warning" else "-"
        lines.append(f"{severity_marker} {p.description}")

    return "\n".join(lines)
