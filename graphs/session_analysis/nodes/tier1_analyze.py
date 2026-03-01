"""Node: Tier 1 AI analysis -- quick summary with structured output.

Uses a lean schema (Tier1Result) to get an AI-refined summary, enhanced
issues (false-positive filtered), and user action tags.  The enhanced
issues are merged back into the programmatic intervals so every interval
carries its final, clean list of issues.

Cost: ~$0.001 per session (Gemini 2.5 Flash)
"""

from __future__ import annotations

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse.decorators import langfuse_context, observe

from common.prompts.session_analysis import (
    format_issues_for_prompt,
    format_tier1_prompt,
)
from common.schemas.session_analysis import (
    Issue,
    SessionAnalysisResult,
    Tier1Result,
)
from graphs.session_analysis.state import SessionAnalysisState
from rrweb.patterns import patterns_to_text


def _get_all_issues(result: SessionAnalysisResult) -> List[Issue]:
    """Flatten issues from all intervals."""
    issues: list[Issue] = []
    for interval in result.intervals:
        issues.extend(interval.issues)
    return issues


def _session_duration(events: list[dict]) -> float:
    if not events:
        return 0.0
    times = [e.get("t", 0.0) for e in events]
    return max(times) - min(times)


@observe(name="session_graph.tier1_analyze")
def tier1_analyze_node(state: SessionAnalysisState) -> dict:
    """Quick AI summary + enhanced issues via structured output.

    Reads:  normalized_events, compressed_events, patterns, prog_result, model
    Writes: result  (SessionAnalysisResult)
    """
    from settings import settings

    events = state["normalized_events"]
    compressed = state["compressed_events"]
    patterns = state.get("patterns", [])
    prog_result = state["prog_result"]
    model = state.get("model", "gemini-2.5-flash")

    duration = _session_duration(events)
    issues = _get_all_issues(prog_result)

    # -- Build prompt --------------------------------------------------
    system, user = format_tier1_prompt(
        duration=duration,
        health_score=prog_result.health_score,
        compressed_events=compressed,
        issues_text=format_issues_for_prompt(issues),
        patterns_text=patterns_to_text(patterns),
    )

    llm = ChatGoogleGenerativeAI(
        api_key=settings.GEMINI_API_KEY,
        model=model,
        temperature=0,
    )

    messages = [SystemMessage(content=system), HumanMessage(content=user)]

    langfuse_handler = langfuse_context.get_current_langchain_handler()
    config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}

    # -- Structured output -> Tier1Result ------------------------------
    tier1: Tier1Result = llm.with_structured_output(Tier1Result).invoke(
        messages, config=config
    )

    result = SessionAnalysisResult(
        intervals=prog_result.intervals,
        summary=tier1.summary,
        title=tier1.title,
        health_score=prog_result.health_score,
        confidence_score=prog_result.confidence_score,
        user_actions=tier1.user_actions,
    )

    return {"result": result}
