"""Node + conditional edges: decide the analysis tier and dispatch.

Tier routing rules:
  - **Tier 0** -- health >= 85 and no issues  -> programmatic only ($0)
  - **Tier 1** -- health 60-85, low-severity  -> quick AI summary  (~$0.001)
  - **Tier 2** -- health < 60 or medium+/visual issues -> full AI + images (~$0.015)

For tier 0, intervals are enriched with compressed event lines which are
far more readable than raw normalised event text.
"""

from __future__ import annotations

import re
from typing import List, Literal, Optional

from common.schemas.session_analysis import (
    TimestampInterval,
    Issue,
    SessionAnalysisResult,
)
from graphs.session_analysis.state import SessionAnalysisState
from rrweb.patterns import BehavioralPattern

TierType = Literal["tier0", "tier1", "tier2"]


def _get_all_issues(prog_result: SessionAnalysisResult) -> List[Issue]:
    """Extract all issues from programmatic result."""
    issues = []
    for interval in prog_result.intervals:
        issues.extend(interval.issues)
    return issues


def _get_max_severity(issues: List[Issue]) -> Optional[str]:
    """Get the maximum severity from a list of issues."""
    if not issues:
        return None

    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_sev = None
    max_val = 0

    for f in issues:
        val = severity_order.get(f.severity, 0)
        if val > max_val:
            max_val = val
            max_sev = f.severity

    return max_sev


def _has_visual_dependent_issues(issues: List[Issue]) -> bool:
    """
    Check if any issues would benefit from visual verification.

    These are issues where the AI needs to SEE the screen to verify:
    - Rage clicks (is the button actually broken?)
    - Dead clicks on buttons (did something visually change?)
    - Form struggles (are there validation errors visible?)
    """
    visual_types = {"rage_click", "dead_click", "form_struggle"}
    return any(f.type in visual_types for f in issues)


def _has_warning_patterns(patterns: List[BehavioralPattern]) -> bool:
    """Check if any behavioral patterns are warnings."""
    return any(p.severity == "warning" for p in patterns)


def route_session(
    prog_result: SessionAnalysisResult,
    behavioral_patterns: List[BehavioralPattern],
) -> TierType:
    """
    Decide which analysis tier to use for this session.

    Tier 0: No AI needed (healthy session, no issues)
    Tier 1: Quick summary only (minor issues)
    Tier 2: Full analysis with images (significant issues)

    Args:
        prog_result: Programmatic analysis result
        behavioral_patterns: Detected behavioral patterns
        session_meta: Optional session metadata (duration, page, etc.)

    Returns:
        TierType: "tier0", "tier1", or "tier2"
    """
    health = prog_result.health_score
    issues = _get_all_issues(prog_result)
    max_severity = _get_max_severity(issues)

    # Tier 0: No AI needed
    # - Health score >= 85 AND no issues
    if health >= 85 and not issues:
        return "tier0"

    # Tier 2: Full analysis with images
    # - Health score < 60 (significant issues)
    # - OR medium/high/critical severity issues
    # - OR visual-dependent issues that need verification
    # - OR warning-level behavioral patterns
    if health < 60:
        return "tier2"

    if max_severity in ("medium", "high", "critical"):
        return "tier2"

    if _has_visual_dependent_issues(issues):
        return "tier2"

    if _has_warning_patterns(behavioral_patterns):
        return "tier2"

    # Tier 1: Quick summary
    # - Health 60-85 with low-severity issues only
    return "tier1"


# -- Node ------------------------------------------------------------------


def route_tier_node(state: SessionAnalysisState) -> dict:
    """Pick an analysis tier based on health score, issues, and patterns.

    Reads:  prog_result, patterns, compressed_events, force_tier (optional)
    Writes: tier, result (baseline -- AI nodes may overwrite for tier1/tier2)
    """
    force_tier = state.get("force_tier")
    prog_result = state["prog_result"]
    patterns = state.get("patterns", [])

    tier = force_tier or route_session(prog_result, patterns)

    return {"tier": tier, "result": prog_result}


# -- Conditional edges -----------------------------------------------------


def after_route_tier(state: SessionAnalysisState) -> str:
    """Three-way dispatch: tier0 -> END, tier1/tier2 -> AI path."""
    return state["tier"]
