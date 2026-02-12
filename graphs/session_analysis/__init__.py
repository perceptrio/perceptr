"""Session Analysis Graph -- tiered rrweb session analysis as a LangGraph.

Each node lives in its own file under ``nodes/`` for readability.
The graph routes sessions through the minimum processing needed::

    START -> normalize -> extract_patterns -> tier0_analyze -> route_tier
      |-- [tier0] ----------------------------------------------------------> END
      |-- [tier1] -> tier1_analyze -> reconcile -----------------------------> END
      +-- [tier2] -> extract_keyframes -> tier2_analyze -> reconcile --------> END

Tier routing
~~~~~~~~~~~~
- **Tier 0** -- health >= 85 and no issues -> programmatic result only ($0)
- **Tier 1** -- health 60-85, low-severity  -> quick AI summary (~$0.001)
- **Tier 2** -- health < 60 or medium+/visual issues -> full AI + images (~$0.015)

Compression runs *before* routing so that:
- Tier 0 intervals get cleaner ``key_events`` from compressed event lines.
- Tier 1/2 already have their compressed text ready for the AI prompt.

Issues per interval
~~~~~~~~~~~~~~~~~~~
- Tier 1/2 AI nodes produce issues **per interval** via structured output.
- The **reconcile** node then compares the AI result with the programmatic
  baseline.  Any medium+ severity issues the AI missed are verified with a
  cheap structured-output call and, if real, inserted back into the
  appropriate interval.

Usage::

    from graphs.session_analysis import SessionAnalyzer

    analyzer = SessionAnalyzer()
    state = analyzer.analyze(raw_session)               # auto-routes
    state = analyzer.analyze(raw, force_tier="tier1")   # force tier

    result = state["result"]   # SessionAnalysisResult
    tier   = state["tier"]     # "tier0" | "tier1" | "tier2"
"""

from __future__ import annotations

from typing import Optional

from langfuse.decorators import observe
from langgraph.graph import END, START, StateGraph

from .nodes.extract_keyframes import extract_keyframes_node
from .nodes.extract_patterns import extract_patterns_node
from .nodes.normalize import normalize_node
from .nodes.reconcile import reconcile_node
from .nodes.route_tier import after_route_tier, route_tier_node
from .nodes.tier0_analyze import tier0_analyze_node
from .nodes.tier1_analyze import tier1_analyze_node
from .nodes.tier2_analyze import tier2_analyze_node
from .state import SessionAnalysisState


def build_session_analysis_graph():
    """Build and compile the session analysis graph."""
    graph = StateGraph(SessionAnalysisState)

    # -- Nodes ---------------------------------------------------------
    graph.add_node("normalize", normalize_node)
    graph.add_node("tier0_analyze", tier0_analyze_node)
    graph.add_node("extract_patterns", extract_patterns_node)
    graph.add_node("route_tier", route_tier_node)
    graph.add_node("extract_keyframes", extract_keyframes_node)
    graph.add_node("tier1_analyze", tier1_analyze_node)
    graph.add_node("tier2_analyze", tier2_analyze_node)
    graph.add_node("reconcile", reconcile_node)

    # -- Linear pipeline: always runs ----------------------------------
    graph.add_edge(START, "normalize")
    graph.add_edge("normalize", "extract_patterns")
    graph.add_edge("extract_patterns", "tier0_analyze")
    graph.add_edge("tier0_analyze", "route_tier")

    # -- Three-way dispatch from route_tier ----------------------------
    graph.add_conditional_edges(
        "route_tier",
        after_route_tier,
        {
            "tier0": END,
            "tier1": "tier1_analyze",
            "tier2": "extract_keyframes",
        },
    )

    # -- AI paths converge on reconcile --------------------------------
    # graph.add_edge("tier1_analyze", "reconcile")
    graph.add_edge("tier1_analyze", END)
    graph.add_edge("extract_keyframes", "tier2_analyze")
    graph.add_edge("tier2_analyze", END)
    # graph.add_edge("tier2_analyze", "reconcile")
    # graph.add_edge("reconcile", END)

    return graph.compile()


# Singleton compiled graph
session_analysis_graph = build_session_analysis_graph()


class SessionAnalyzer:
    """High-level API wrapping the session analysis graph.

    Example::

        analyzer = SessionAnalyzer()
        state = analyzer.analyze(raw_session_dict)
        print(state["result"].summary)
    """

    def __init__(self) -> None:
        self.graph = session_analysis_graph

    @observe(name="session_analysis_graph")
    def analyze(
        self,
        raw_session: dict,
        *,
        force_tier: Optional[str] = None,
        model: str = "gemini-2.5-flash-preview-09-2025",
        max_frames: int = 8,
    ) -> dict:
        """Run the full session analysis graph.

        Args:
            raw_session: Raw rrweb payload ``{sessionId, startTime, endTime, data}``.
            force_tier: Override tier routing (``"tier0"``, ``"tier1"``, ``"tier2"``).
            model: Gemini model name.
            max_frames: Maximum keyframes to extract for tier 2.

        Returns:
            Final graph state.  Access ``state["result"]`` for the
            ``SessionAnalysisResult`` and ``state["tier"]`` for the selected tier.
        """
        initial_state: dict = {
            "raw_session": raw_session,
            "model": model,
            "max_frames": max_frames,
        }
        if force_tier is not None:
            initial_state["force_tier"] = force_tier

        return self.graph.invoke(initial_state)
