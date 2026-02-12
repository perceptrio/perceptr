"""
Semantic event compression for LLM input optimization.

Converts verbose normalized events into a compact, human-readable timeline
that preserves context while reducing token count by 60-80%.

Pipeline:
  1. Parse events → skip noise, extract structured fields, clean labels
  2. Merge consecutive duplicates (clicks on same target, scrolls, etc.)
  3. Group nearby form fills into single "Filled form: …" lines
  4. Overlay finding markers (kind-aware: rage_click suppresses clicks only, etc.)
  5. Format as a compact text timeline
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from common.schemas.session_analysis import SessionAnalysisResult
from common.types import (
    SIGNAL_RAGE_CLICK,
    SIGNAL_DEAD_CLICK,
    SIGNAL_NAVIGATION_LOOP,
    SIGNAL_FORM_STRUGGLE,
    SIGNAL_SCROLL_THRASHING,
)

# ── Config ───────────────────────────────────────────────────────────────────

NOISE_PREFIXES = (
    "user moved mouse",
    "user focus on",
    "user blur ",
    "viewport resized",
    "user double-click",  # individual clicks already captured
)

# Max seconds between events to merge them (same kind + target)
MERGE_WINDOW_S = 3.0

# Map finding types → which event kind they describe (for selective suppression)
_FINDING_SUPPRESSES = {
    SIGNAL_RAGE_CLICK: "click",
    SIGNAL_DEAD_CLICK: "click",
    SIGNAL_NAVIGATION_LOOP: "navigate",
    SIGNAL_SCROLL_THRASHING: "scroll",
    SIGNAL_FORM_STRUGGLE: "input",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  1. Clean element labels
# ═══════════════════════════════════════════════════════════════════════════════


def _clean_label(raw: str, max_len: int = 50) -> str:
    """Turn verbose rrweb element description into a short readable label.

    Examples:
      'button "Reserve Your Spot"'  →  '"Reserve Your Spot" button'
      'input "placeholder:email | name:email | …"'  →  '"email" input'
      'select "value:Founder | Founder | …"'  →  'select'  (or '"role" select')
    """
    if not raw:
        return "element"

    m = re.match(r'^(\w+)\s+"(.*)"$', raw.strip(), re.DOTALL)
    if not m:
        return raw[:max_len] if len(raw) > max_len else raw

    elem = m.group(1)
    content = m.group(2).strip()

    if "|" in content:
        label = _best_label_from_pipes(content)
        return f'"{label}" {elem}' if label else elem

    if len(content) <= max_len:
        return f'"{content}" {elem}'

    return f'"{content[:max_len - 1]}…" {elem}'


def _best_label_from_pipes(content: str) -> str | None:
    """Pick the best human-readable token from pipe-separated rrweb attrs."""
    parts = [p.strip() for p in content.split("|")]

    for prefix in ("aria-label:", "name:", "placeholder:"):
        for p in parts:
            if p.startswith(prefix):
                return p[len(prefix) :]

    # type:submit → look for adjacent plain-text label
    for p in parts:
        if p.strip() == "type:submit":
            for other in parts:
                if ":" not in other and other.strip() and len(other.strip()) < 30:
                    return other.strip()
            return "Submit"

    # First short non-attribute part
    for p in parts:
        clean = p.strip()
        if ":" not in clean and clean and len(clean) < 40:
            return clean

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  2. Parse events
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class _Evt:
    """A parsed, cleaned event."""

    t: float
    kind: str  # click | scroll | navigate | input | select | network | console | other
    target: str  # cleaned label
    value: str  # URL, input value, network detail, console message …
    raw: str  # original event string
    interactive: bool | None = None  # whether clicked element has triggers


def _parse_event(ev: dict) -> _Evt | None:
    """Parse one normalized-event dict into an _Evt.  Returns None to skip noise."""
    t = ev.get("t", 0.0)
    e: str = ev.get("e", "")

    if any(e.startswith(p) for p in NOISE_PREFIXES):
        return None

    if e.startswith("user click on "):
        raw_target = e[14:]
        # html / body clicks are background clicks (dismissing dropdown, etc.)
        if raw_target.startswith("html ") or raw_target.startswith("body "):
            return None  # skip – not meaningful
        interactive = ev.get("interactive")
        return _Evt(
            t, "click", _clean_label(raw_target), "", e, interactive=interactive
        )

    if "user scrolled through page" in e:
        m = re.search(r"y=([-\d.]+)", e)
        return _Evt(t, "scroll", "page", m.group(1) if m else "?", e)

    if e.startswith("user navigated to "):
        return _Evt(t, "navigate", e[18:].strip(), "", e)

    if e.startswith("user typed in "):
        rest = e[14:]
        if ': "' in rest:
            tgt, val = rest.split(': "', 1)
            val = val.rstrip('"')
            return _Evt(t, "input", _clean_label(tgt), val[:30], e)
        return _Evt(t, "input", _clean_label(rest), "", e)

    if e.startswith("user set ") and " to " in e:
        rest = e[9:]
        tgt, val = rest.split(" to ", 1)
        return _Evt(t, "select", _clean_label(tgt), val.strip(), e)

    if e.startswith("network:"):
        return _Evt(t, "network", "", e[8:].strip(), e)

    if e.startswith("console ["):
        m = re.match(r"console \[(\w+)\]:\s*(.*)", e)
        if m:
            return _Evt(t, "console", m.group(1), m.group(2)[:100], e)
        return _Evt(t, "console", "log", e[:80], e)

    return _Evt(t, "other", "", e[:80], e)


# ═══════════════════════════════════════════════════════════════════════════════
#  3. Merge consecutive duplicate events
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class _Merged:
    """One or more consecutive similar events collapsed together."""

    t_start: float
    t_end: float
    kind: str
    target: str
    count: int = 1
    values: list[str] = field(default_factory=list)
    interactive: bool | None = None  # for clicks: whether element has triggers


def _merge_events(events: list[_Evt]) -> list[_Merged]:
    """Merge consecutive events of the same kind+target within MERGE_WINDOW_S.

    Special rules:
      - Scrolls always merge regardless of target
      - Consecutive input/select merge (form fill grouping, step 1)
    """
    if not events:
        return []

    out: list[_Merged] = []
    cur = _Merged(
        t_start=events[0].t,
        t_end=events[0].t,
        kind=events[0].kind,
        target=events[0].target,
        values=[events[0].value] if events[0].value else [],
        interactive=events[0].interactive,
    )

    for ev in events[1:]:
        dt = ev.t - cur.t_end
        merge = False

        if dt < MERGE_WINDOW_S:
            if ev.kind == cur.kind and ev.target == cur.target:
                merge = True
            elif ev.kind == "scroll" and cur.kind == "scroll":
                merge = True
            elif ev.kind in ("input", "select") and cur.kind in ("input", "select"):
                merge = True

        if merge:
            cur.t_end = ev.t
            cur.count += 1
            if ev.value:
                cur.values.append(ev.value)
            if ev.kind in ("input", "select") and ev.target != cur.target:
                cur.target = ""  # mixed targets → will show as generic "form"
        else:
            out.append(cur)
            cur = _Merged(
                t_start=ev.t,
                t_end=ev.t,
                kind=ev.kind,
                target=ev.target,
                values=[ev.value] if ev.value else [],
                interactive=ev.interactive,
            )

    out.append(cur)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  4. Group nearby form fills (absorb interstitial clicks)
# ═══════════════════════════════════════════════════════════════════════════════


_GENERIC_TARGETS = {"input", "element", "checkbox", "div", "span", "button", "select"}


def _is_generic_target(target: str) -> bool:
    """True if the target is too generic to be useful as a label."""
    return target.lower().strip() in _GENERIC_TARGETS


def _has_form_event_ahead(merged: list[_Merged], start: int, max_look: int = 4) -> bool:
    """Check if there's an input/select event in the next few items."""
    for k in range(start, min(start + max_look, len(merged))):
        if merged[k].kind in ("input", "select"):
            return True
    return False


def _checkbox_label(click_target: str, set_target: str) -> str:
    """Build a checkbox label: prefer the click target (has the readable name)."""
    if click_target and click_target != "input" and click_target != "element":
        return click_target
    if set_target and set_target != "input" and set_target != "element":
        return set_target
    return "checkbox"


def _group_form_fills(merged: list[_Merged]) -> list[_Merged]:
    """Collapse sequences of form events into single summary lines.

    Absorbs:
      - clicks between form fields (focus clicks, dropdown opens)
      - clicks immediately BEFORE the first form field
      - checkbox patterns: click "label" → click input → set checked
    """
    result: list[_Merged] = []
    i = 0

    while i < len(merged):
        m = merged[i]

        if m.kind not in ("input", "select"):
            result.append(m)
            i += 1
            continue

        # Absorb preceding clicks (field focus, label clicks)
        last_click_target = ""
        while (
            result
            and result[-1].kind == "click"
            and (m.t_start - result[-1].t_end) < 2.0
        ):
            popped = result.pop()
            if popped.target and not _is_generic_target(popped.target):
                last_click_target = popped.target

        # Collect the form sequence going forward
        form_values = _checkbox_value(m, last_click_target)
        t_start = m.t_start
        t_end = m.t_end
        last_click_target = ""
        j = i + 1

        while j < len(merged):
            nxt = merged[j]
            gap = nxt.t_start - t_end
            if gap > 5.0:
                break

            if nxt.kind in ("input", "select"):
                form_values.extend(_checkbox_value(nxt, last_click_target))
                last_click_target = ""
                t_end = nxt.t_end
                j += 1
            elif nxt.kind == "click" and gap < 2.0:
                # Absorb clicks if a form event is coming soon
                if _has_form_event_ahead(merged, j + 1):
                    # Remember target for checkbox labels, but only if it's
                    # descriptive (skip generic "input", "element", etc.)
                    if nxt.target and not _is_generic_target(nxt.target):
                        last_click_target = nxt.target
                    t_end = nxt.t_end
                    j += 1
                else:
                    break
            else:
                break

        if j > i + 1:
            result.append(
                _Merged(
                    t_start=t_start,
                    t_end=t_end,
                    kind="input",
                    target="",
                    count=len(form_values),
                    values=form_values,
                )
            )
            i = j
        else:
            result.append(
                _Merged(
                    t_start=m.t_start,
                    t_end=m.t_end,
                    kind="input",
                    target=m.target,
                    count=m.count,
                    values=form_values,
                )
            )
            i += 1

    return result


def _extract_name(label: str) -> str:
    """Extract just the name from a cleaned label like '"Foo" button' → 'Foo'."""
    m = re.match(r'^"([^"]+)"', label)
    return m.group(1) if m else label


def _checkbox_value(m: _Merged, last_click_target: str) -> list[str]:
    """Build form value list for a merged event, using click context for checkboxes."""
    if m.values in (["on"], ["checked"]):
        label = _checkbox_label(last_click_target, m.target)
        return [f"✓ {_extract_name(label)}"]
    if m.values in (["off"], ["unchecked"]):
        label = _checkbox_label(last_click_target, m.target)
        return [f"✗ {_extract_name(label)}"]
    return list(m.values)


# ═══════════════════════════════════════════════════════════════════════════════
#  5. Finding overlay (kind-aware suppression)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class _FindingSpan:
    """A time range associated with a finding marker."""

    t_start: float
    t_end: float
    marker: str
    suppress_kind: str  # only suppress this event kind in the window
    uid: str = ""  # unique id for deduplication (timestamp + type)


def _build_finding_spans(
    prog_result: SessionAnalysisResult | None,
) -> list[_FindingSpan]:
    """Build finding spans from programmatic results.

    Each span records WHICH event kind it suppresses, so a dead-click finding
    won't accidentally swallow nearby form fills or console errors.
    """
    if not prog_result:
        return []

    spans: list[_FindingSpan] = []
    for interval in prog_result.intervals:
        for f in interval.issues:
            t = _mmss_to_seconds(f.timestamp)
            sev = "[!!]" if f.severity in ("high", "critical") else "[!]"
            # Clean up the root_cause text (may contain raw rrweb element dumps)
            desc = _clean_finding_text(f.root_cause, 80)
            marker = f"  {sev} {f.type.upper()}: {desc}"
            suppress = _FINDING_SUPPRESSES.get(f.type, "click")

            uid = f"{f.type}_{f.timestamp}_{f.target or ''}"

            # Tighter windows for dead clicks, wider for rage clicks
            if f.type == "dead_click":
                spans.append(_FindingSpan(t - 0.5, t + 1.5, marker, suppress, uid))
            elif f.type in ("rage_click", "scroll_thrashing"):
                spans.append(_FindingSpan(t - 1.0, t + 4.0, marker, suppress, uid))
            else:
                spans.append(_FindingSpan(t - 0.5, t + 2.0, marker, suppress, uid))

    return spans


def _clean_finding_text(text: str, max_len: int = 80) -> str:
    """Clean up finding root_cause text: shorten verbose element descriptions."""
    if not text:
        return ""

    # Replace verbose quoted element descriptions with cleaned versions
    def _replace_quoted(match: re.Match) -> str:
        elem_desc = match.group(1)
        if "|" in elem_desc:
            label = _best_label_from_pipes(elem_desc)
            return f'"{label}"' if label else "element"
        if len(elem_desc) > 40:
            return f'"{elem_desc[:37]}…"'
        return f'"{elem_desc}"'

    cleaned = re.sub(r'"([^"]{20,})"', _replace_quoted, text)
    return cleaned[:max_len] if len(cleaned) > max_len else cleaned


def _mmss_to_seconds(ts: str) -> float:
    parts = ts.split(":")
    return int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else 0.0


def _is_suppressed(m: _Merged, spans: list[_FindingSpan]) -> bool:
    """True if this merged event should be hidden because a finding already
    describes it (kind-aware: only suppresses matching event kinds)."""
    for span in spans:
        if m.kind == span.suppress_kind:
            if m.t_start >= span.t_start and m.t_end <= span.t_end:
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  6. Formatting
# ═══════════════════════════════════════════════════════════════════════════════


def _fmt_merged(m: _Merged) -> str:
    """Format one merged event into a single output line."""

    if m.kind == "navigate":
        return f"→ Navigated to {m.target}"

    if m.kind == "click":
        # Annotate non-interactive elements so the LLM knows it's likely a UX issue
        trigger_hint = ""
        if m.interactive is False:
            trigger_hint = " and no triggers"
        if m.count > 2:
            return f"Clicked {m.target}{trigger_hint} ({m.count} times)"
        if m.count == 2:
            return f"Clicked {m.target}{trigger_hint} (twice)"
        return f"→ Clicked {m.target}{trigger_hint}"

    if m.kind in ("input", "select"):
        vals = [v for v in m.values if v]
        if vals:
            if len(vals) <= 5:
                return f"Filled form: {' → '.join(vals)}"
            return f"Filled form ({len(vals)} fields): {' → '.join(vals[:4])}…"
        label = m.target or "form"
        return f"Interacted with {label}"

    if m.kind == "scroll":
        ys = []
        for v in m.values:
            try:
                ys.append(float(v))
            except (ValueError, TypeError):
                pass
        if len(ys) >= 2:
            changes = sum(
                1
                for i in range(2, len(ys))
                if (ys[i] - ys[i - 1]) * (ys[i - 1] - ys[i - 2]) < 0
            )
            if changes > 2:
                return f"Scrolled back and forth ({changes} dir changes) — searching behavior"
            direction = "down" if ys[-1] > ys[0] else "up"
            return f"Scrolled {direction} (y={ys[0]:.0f}→{ys[-1]:.0f})"
        return f"Scrolled ({m.count} events)"

    if m.kind == "network":
        if m.values:
            return f"Network: {'; '.join(m.values[:3])}"
        return f"Network request"

    if m.kind == "console":
        level = m.target or "log"
        msgs = [v for v in m.values if v]
        if msgs:
            suffix = f" (+{len(msgs)-1} more)" if len(msgs) > 1 else ""
            return f"Console [{level}]: {msgs[0][:80]}{suffix}"
        return f"Console [{level}]"

    if m.values:
        return f"{m.values[0]}"
    return f"Activity"


# ═══════════════════════════════════════════════════════════════════════════════
#  7. Main entry point
# ═══════════════════════════════════════════════════════════════════════════════


def compress_events(
    normalized_events: list[dict],
    prog_result: SessionAnalysisResult | None = None,
    *,
    max_lines: int = 60,
) -> str:
    """Compress normalized events into a semantic timeline for LLM input.

    Args:
        normalized_events: list of dicts with 't' and 'e' keys
        prog_result: optional programmatic result (adds finding markers)
        max_lines: cap on output lines

    Returns:
        Compact text timeline of the session.
    """
    # Parse
    parsed = [p for ev in normalized_events if (p := _parse_event(ev)) is not None]
    if not parsed:
        return "No significant events recorded."

    # Merge consecutive duplicates
    merged = _merge_events(parsed)

    # Group nearby form fills (absorb intermediate clicks)
    merged = _group_form_fills(merged)

    # Build finding spans
    spans = _build_finding_spans(prog_result)

    # Format
    lines: list[str] = []
    emitted: set[str] = set()  # tracks by uid to avoid dedup collisions

    for m in merged:
        # Emit finding markers whose time overlaps this event
        for span in spans:
            overlaps = m.t_start <= span.t_end and m.t_end >= span.t_start
            if overlaps and span.uid not in emitted:
                lines.append(span.marker)
                emitted.add(span.uid)

        # Skip if a finding already describes this event (kind-aware)
        if _is_suppressed(m, spans):
            continue

        line = _fmt_merged(m)
        if line:
            lines.append(line)

    # Emit any remaining finding markers not yet placed
    for span in spans:
        if span.uid not in emitted:
            lines.append(span.marker)
            emitted.add(span.uid)

    # Trim
    if len(lines) > max_lines:
        half = max_lines // 2
        lines = (
            lines[:half]
            + [f"  … ({len(lines) - max_lines} lines omitted) …"]
            + lines[-half:]
        )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  8. Stats helper
# ═══════════════════════════════════════════════════════════════════════════════


def get_compression_stats(
    original_events: list[dict],
    compressed_text: str,
) -> dict:
    """Return compression ratio and estimated token savings."""
    original_text = "\n".join(
        f"{e.get('t', 0):.2f}s  {e.get('e', '')}" for e in original_events
    )
    orig = len(original_text)
    comp = len(compressed_text)

    return {
        "original_events": len(original_events),
        "original_chars": orig,
        "compressed_chars": comp,
        "compression_ratio": round(1 - comp / orig, 2) if orig else 0,
        "estimated_tokens_saved": (orig - comp) // 4,
    }
