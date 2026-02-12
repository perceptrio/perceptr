"""Node: extract behavioural patterns from the normalised timeline.

Patterns (hesitation, navigation confusion, search behaviour, etc.)
feed into the tier router and give the AI nodes richer context.
"""

from __future__ import annotations

from graphs.session_analysis.state import SessionAnalysisState
from rrweb.patterns import extract_patterns


def extract_patterns_node(state: SessionAnalysisState) -> dict:
    """Detect high-level behavioural patterns.

    Reads:  normalized_events
    Writes: patterns  (List[BehavioralPattern])
    """
    events = state["normalized_events"]
    patterns = extract_patterns(events)
    return {"patterns": patterns}
