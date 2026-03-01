"""Node: Tier 2 AI analysis -- full analysis with optional keyframe images.

Uses a vision model to produce a complete SessionAnalysisResult with
AI-written intervals, issues, summary, and scores.  When keyframes are
available, the model can verify visual effects (loading states, error
messages, layout shifts) that event logs alone cannot capture.

Issues are produced per-interval via structured output, so there is no
need for a separate reconciliation pass -- the AI returns a clean issue
list for every interval.

Cost: ~$0.01-0.015 per session (Gemini 2.5 Flash)
"""

from __future__ import annotations

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse.decorators import langfuse_context, observe

from common.prompts.session_analysis import (
    format_issues_for_prompt,
    format_tier2_prompt,
)
from common.schemas.session_analysis import (
    Issue,
    SessionAnalysisResult,
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


def _page_url(raw_session: dict, events: list[dict]) -> str:
    """Extract page URL from first navigation or session metadata."""
    for ev in events:
        e = ev.get("e", "")
        if "navigated to" in e:
            return e.split("navigated to ", 1)[1].strip()
    return raw_session.get("url", raw_session.get("href", "Unknown"))


def _build_multimodal_content(
    user_prompt: str,
    keyframe_base64: list,
) -> list[dict]:
    """Interleave text prompt with keyframe screenshots."""
    parts: list[dict] = [{"type": "text", "text": user_prompt}]
    for _time_s, data_url in keyframe_base64:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": data_url, "detail": "low"},
            }
        )
    return parts


@observe(name="session_graph.tier2_analyze")
def tier2_analyze_node(state: SessionAnalysisState) -> dict:
    """Full AI analysis with images via structured output.

    Reads:  raw_session, normalized_events, compressed_events, patterns,
            prog_result, model, keyframe_base64
    Writes: result  (SessionAnalysisResult)
    """
    from settings import settings

    raw_session = state["raw_session"]
    events = state["normalized_events"]
    compressed = state["compressed_events"]
    patterns = state.get("patterns", [])
    prog_result = state["prog_result"]
    model = state.get("model", "gemini-2.5-flash")
    keyframe_base64 = state.get("keyframe_base64", [])

    duration = _session_duration(events)
    url = _page_url(raw_session, events)
    issues = _get_all_issues(prog_result)

    # -- Build prompt --------------------------------------------------
    system, user = format_tier2_prompt(
        duration=duration,
        page_url=url,
        compressed_events=compressed,
        patterns_text=patterns_to_text(patterns),
        programmatic_issues=format_issues_for_prompt(issues),
        image_count=len(keyframe_base64),
    )

    llm = ChatGoogleGenerativeAI(
        api_key=settings.GEMINI_API_KEY,
        model=model,
        temperature=0,
    )

    # -- Messages (with images if available) ---------------------------
    if keyframe_base64:
        content = _build_multimodal_content(user, keyframe_base64)
        messages = [SystemMessage(content=system), HumanMessage(content=content)]
    else:
        messages = [SystemMessage(content=system), HumanMessage(content=user)]

    langfuse_handler = langfuse_context.get_current_langchain_handler()
    config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}

    # -- Structured output -> full SessionAnalysisResult ---------------
    result: SessionAnalysisResult = llm.with_structured_output(
        SessionAnalysisResult, method="function_calling"
    ).invoke(messages, config=config)

    return {"result": result}
