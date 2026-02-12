"""Node: normalize raw rrweb events into an LLM-friendly format.

Transforms raw rrweb event payloads (clicks, scrolls, mutations, etc.)
into timestamped, human-readable event dicts that downstream nodes can
consume without caring about the rrweb wire format.
"""

from __future__ import annotations

from graphs.session_analysis.state import SessionAnalysisState
from rrweb.normalizer import normalize_events, normalized_events_to_dict_list


def normalize_node(state: SessionAnalysisState) -> dict:
    """Parse raw rrweb events into timestamped, human-readable event dicts.

    Reads:  raw_session
    Writes: normalized_events
    """
    raw_session = state["raw_session"]
    normalized = normalize_events(raw_session, collapse_scroll_ms=800)
    events_list = normalized_events_to_dict_list(normalized)
    return {"normalized_events": events_list}
