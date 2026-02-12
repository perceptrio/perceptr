"""State definition for the session analysis graph."""

from __future__ import annotations

from typing import Optional

from typing_extensions import TypedDict

from common.schemas.session_analysis import SessionAnalysisResult


class SessionAnalysisState(TypedDict, total=False):
    """Shared state flowing through the session analysis graph.

    Every node reads what it needs and writes its outputs back.
    ``total=False`` lets each node set only the fields it produces.

    Graph flow::

        START -> normalize -> heuristics -> extract_patterns -> route_tier
          |-- [tier0] ---------------------------------------------------> END
          +-- [needs_ai] -> compress --+-- [tier1] -> tier1_analyze -----> END
                                       +-- [tier2] -> extract_keyframes -> tier2_analyze -> END
    """

    # -- Inputs (set before graph invocation) --------------------------
    raw_session: dict  # Raw rrweb payload {sessionId, startTime, endTime, data}
    model: str  # LLM model name (default: gemini-2.5-flash)
    reconcile_model: (
        str  # LLM model name for reconciliation (default: gpt-5-mini-2025-08-07)
    )
    max_frames: int  # Max keyframes for tier2 (default: 8)
    force_tier: Optional[str]  # Override tier routing (for testing)

    # -- After: normalize ----------------------------------------------
    normalized_events: list[dict]

    # -- After: heuristics ---------------------------------------------
    prog_result: SessionAnalysisResult

    # -- After: extract_patterns ---------------------------------------
    patterns: list  # List[BehavioralPattern]

    # -- After: route_tier ---------------------------------------------
    tier: str  # "tier0" | "tier1" | "tier2"

    # -- After: compress -----------------------------------------------
    compressed_events: str

    # -- After: extract_keyframes (tier2 only) -------------------------
    keyframe_base64: list  # List of (timestamp_s, data_url)

    # -- Final output --------------------------------------------------
    result: SessionAnalysisResult
