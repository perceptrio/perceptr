"""Node: reconcile programmatic and AI issues via structured output.

After the AI analysis (tier 1 or tier 2) produces its result, the
reconciler verifies if issues are real or false positives (noisy).

Medium+ severity discrepancies are verified with a cheap structured-output
LLM call.  Verified "real" issues are inserted back into the appropriate
intervals so each interval always carries a complete, clean issue list.

"""

from __future__ import annotations

from typing import List, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langfuse.decorators import langfuse_context, observe
from pydantic import BaseModel, Field

from common.schemas.session_analysis import (
    Issue,
    TimestampInterval,
)
from graphs.session_analysis.state import SessionAnalysisState


# -- Structured output schema ----------------------------------------------


class IssueVerification(BaseModel):
    """Classification for a single discrepant issue."""

    issue_index: int = Field(description="1-based index of the issue being verified")
    classification: Literal["real", "false_positive", "low_priority"] = Field(
        description=(
            "real = genuine UX issue or bug that should be reported, "
            "false_positive = normal behaviour misclassified, "
            "low_priority = technically an issue but too minor to report"
        ),
    )
    reason: str = Field(
        description="Brief reason for this classification (max 100 chars)"
    )


class ReconcileOutput(BaseModel):
    """Structured output returned by the verification LLM call."""

    verifications: List[IssueVerification] = Field(
        description="One classification entry per issue that was verified"
    )


# -- Prompts ---------------------------------------------------------------

RECONCILE_SYSTEM = """\
You are reviewing automated UX and bug issue detections that need verification.

For each issue, classify it as:
- **real**: genuine UX issue that should be reported
- **false_positive**: noise in the data, not a real issue
- **low_priority**: technically an issue but too minor to report

Use the compressed session timeline as context to decide."""

RECONCILE_USER = """\
## Session Timeline (compressed)
{compressed_events}

## Issues to Verify
These were detected by our analysis pipeline Classify each one. Verify if this is noisy data or a real issue.

{issues_list}

"""


# -- Helpers ---------------------------------------------------------------


def _mmss_to_seconds(mmss: str) -> float:
    parts = mmss.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _insert_issues_into_intervals(
    intervals: list[TimestampInterval],
    issues: List[Issue],
) -> list[TimestampInterval]:
    """Insert issues into the intervals whose time range contains them."""
    updated = []
    for interval in intervals:
        start_s = _mmss_to_seconds(interval.start_time)
        end_s = _mmss_to_seconds(interval.end_time)

        matching = [
            issue
            for issue in issues
            if start_s <= _mmss_to_seconds(issue.timestamp) < end_s
        ]

        # we overwrite the issues with the matching issues
        updated.append(interval.model_copy(update={"issues": matching}))
    return updated


# -- Node ------------------------------------------------------------------


@observe(name="session_graph.reconcile")
def reconcile_node(state: SessionAnalysisState) -> dict:
    """Verify discrepant issues between programmatic and AI results.

    Only runs an LLM call when there are medium+ severity programmatic
    issues that the AI did not flag.  Verified "real" issues are added
    back to the appropriate intervals in the result.

    Reads:  prog_result, result, compressed_events, model
    Writes: result (updated with any verified real issues)
    """
    from settings import settings

    ai_result = state["result"]
    compressed = state.get("compressed_events", "")
    reconcile_model = state.get("reconcile_model", "gpt-5-mini-2025-08-07")

    # Flatten issues from both sources
    ai_issues = [i for intv in ai_result.intervals for i in intv.issues]

    # Only verify medium+ severity (low-severity discrepancies aren't worth a call)
    worth_verifying = [
        i for i in ai_issues if i.severity in ("medium", "high", "critical")
    ]
    if not worth_verifying:
        return {}  # Nothing to change — keep AI result as-is

    issues_text = "\n".join(
        f"[{idx + 1}] {issue.severity.upper()} {issue.type}: {issue.root_cause}"
        for idx, issue in enumerate[Issue](worth_verifying)
    )
    # -- Structured-output verification --------------------------------
    llm = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=reconcile_model,
    )
    messages = [
        SystemMessage(content=RECONCILE_SYSTEM),
        HumanMessage(
            content=RECONCILE_USER.format(
                compressed_events=compressed,
                issues_list=issues_text,
            )
        ),
    ]

    langfuse_handler = langfuse_context.get_current_langchain_handler()
    config = {"callbacks": [langfuse_handler]} if langfuse_handler else {}

    output: ReconcileOutput = llm.with_structured_output(ReconcileOutput).invoke(
        messages, config=config
    )
    # -- Collect verified real issues ----------------------------------
    real_issues: list[Issue] = []
    for v in output.verifications:
        idx = v.issue_index - 1  # Convert to 0-based
        if 0 <= idx < len(worth_verifying) and v.classification == "real":
            real_issues.append(worth_verifying[idx])
    if not real_issues:
        return {}  # All discrepancies were false positives or low priority
    # -- Add verified issues back into appropriate intervals -----------
    updated_intervals = _insert_issues_into_intervals(ai_result.intervals, real_issues)
    updated_result = ai_result.model_copy(update={"intervals": updated_intervals})
    return {"result": updated_result}
