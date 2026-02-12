"""
Prompt templates for tiered session analysis.

Each tier has specific input/output requirements optimized for cost and quality.
"""

from __future__ import annotations

from common.schemas.session_analysis import Issue

# =============================================================================
# TIER 1: Quick Summary Prompt
# =============================================================================
# Input: Programmatic issues + behavioral patterns (compact)
# Output: 2-3 sentence human narrative
# Target: ~200 output tokens
# =============================================================================

TIER1_SUMMARY_SYSTEM = """You are a UX researcher producing a quick structured analysis of a user session.

You will receive compressed event data, automated issues (may contain false positives), and behavioral patterns.

Your task: Return structured output with these fields:

1. **title**: Short title summarizing the main user task (max 100 chars).

2. **summary**: 2-3 sentence summary of what the user did and what went wrong (if anything).
   - Be specific: use element names, timestamps, and actions
   - Sound like a human analyst, not a report
   - Max 200 characters

3. **user_actions**: Tag the user's actions/emotional state as a list (max 8 tags).
   Examples: hesitant, confused, frustrated, exploring, onboarding, purchasing, form_filling, browsing, searching, stuck, blocked"""

TIER1_SUMMARY_USER = """Session Facts:
- Duration: {duration}s
- Health Score: {health_score}/100
- Compressed Session Data:
{compressed_events}

Detected Issues (may contain false positives):
{issues_text}

Behavioral Patterns:
{patterns_text}

Analyze this session and return the structured result."""


# =============================================================================
# TIER 2: Full Analysis Prompt (with optional images)
# =============================================================================
# Input: Compressed events + behavioral patterns + prog issues + images
# Output: Full analysis with narrative, issues, root cause
# Target: ~500-800 output tokens
# =============================================================================

TIER2_FULL_SYSTEM = """You are a senior UX researcher analyzing a user session recording.

You will receive:
1. Compressed event timeline (key actions, not every event)
2. Behavioral patterns detected by automated analysis
3. Programmatic issues (may contain false positives)
4. Screenshots at key moments (if provided)

Your task: Produce a structured analysis with:

**1. Title**: Short title summarizing the main user task (e.g., "Form submission with unresponsive button")

**2. Summary**: describe:
   - What the user was trying to accomplish
   - What happened during the session
   - How the user responded to any issues
   - The overall experience quality
   - NO MORE THAN 200 CHARACTERS

**3. Issues**: List ONLY real issues (filter out false positives from automated detection)
   For each issue, provide:
   - type: rage_click | dead_click | navigation_loop | form_struggle | scroll_thrashing | unknown
   - severity: low | medium | high | critical
   - root_cause: Your hypothesis about WHY this happened (technical cause) and correlate with events and screenshots elements if provided in less than 400 characters
   - reproduction_steps: How to recreate this issue
   - category: BUG | USABILITY_ISSUE | PERFORMANCE_ISSUE | ENHANCEMENT

**4. Health Score**: 0-100 (100 = perfect session, lower = more friction)

**5. Confidence Score**: 0-1 (how confident you are in this analysis)

**6. User Actions**: describe the user's actions during the session
   - What was he feeling? [hesitant, confused, frustrated, ..etc]
   - What was the user's goal? [onboarded, checkedout, purchased, ..etc]
   - this is a list of actions, no more than 8 actions and write action as tag

**7. Intervals / key_events**: For each interval, set key_events to 3–5 key moments. Each key event has:
   - timestamp (str): MM:SS when it happened
   - description (str): short human-readable description of what happened at that moment (same idea as timestamp_descriptions).

Guidelines:
- Be specific: "User clicked 'Reserve Your Spot' 8 times in 2.6s" not "User clicked repeatedly"
- For root_cause, think technically: "Button click handler doesn't show loading state or disable during submission"
- If images are provided, use them to identify visual issues (error messages, loading states, layout problems)
- If images are provided, use them to correlate with events and root cause
- Filter out obvious false positives from automated issues
- Focus on actionable insights"""

TIER2_FULL_USER = """## Session Data

Duration: {duration}s
Page/URL: {page_url}

## Event Timeline (Compressed)
{compressed_events}

## Behavioral Patterns
{patterns_text}

## Automated Issues (may contain false positives)
{programmatic_issues}

{images_instruction}

Analyze this session and return the structured result."""

TIER2_IMAGES_INSTRUCTION = """## Screenshots
{image_count} screenshots are provided at key moments. Use them to:
- Verify if clicks had visible effects (success messages, loading states)
- Identify visual/UI issues not visible in event logs
- Confirm or reject automated issues"""

TIER2_NO_IMAGES_INSTRUCTION = """Note: No screenshots available for this session. Analysis is based on event logs only."""


# =============================================================================
# RECONCILE: Verify discrepant issues
# =============================================================================
# Input: List of programmatic issues AI didn't flag
# Output: Classification for each
# Target: ~100 output tokens
# =============================================================================

RECONCILE_SYSTEM = """You are reviewing automated UX and bug detection issues that need verification.

For each issue, classify it as:
- REAL: This is a genuine UX issue that should be reported
- FALSE_POSITIVE: This is normal behavior misclassified as an issue
- LOW_PRIORITY: This is technically an issue but too minor to report

Be brief - just the classification and a short reason."""

RECONCILE_USER = """These issues were detected by automated rules but weren't flagged by initial AI analysis.
Review each one based on the session context:

Session Context:
{compressed_events}

Issues to verify:
{issues_list}

For each issue, respond with: [INDEX] CLASSIFICATION: reason"""


# =============================================================================
# Helper functions to format prompts
# =============================================================================


def format_tier1_prompt(
    compressed_events: str,
    duration: float,
    health_score: float,
    issues_text: str,
    patterns_text: str,
) -> tuple[str, str]:
    """Format Tier 1 prompt pair (system, user)."""
    user = TIER1_SUMMARY_USER.format(
        compressed_events=compressed_events,
        duration=int(duration),
        health_score=int(health_score),
        issues_text=issues_text or "None detected",
        patterns_text=patterns_text or "No significant patterns",
    )
    return TIER1_SUMMARY_SYSTEM, user


def format_tier2_prompt(
    duration: float,
    page_url: str,
    compressed_events: str,
    patterns_text: str,
    programmatic_issues: str,
    image_count: int = 0,
) -> tuple[str, str]:
    """Format Tier 2 prompt pair (system, user)."""
    if image_count > 0:
        images_instruction = TIER2_IMAGES_INSTRUCTION.format(image_count=image_count)
    else:
        images_instruction = TIER2_NO_IMAGES_INSTRUCTION

    user = TIER2_FULL_USER.format(
        duration=int(duration),
        page_url=page_url or "Unknown",
        compressed_events=compressed_events,
        patterns_text=patterns_text or "No significant patterns",
        programmatic_issues=programmatic_issues or "None detected",
        images_instruction=images_instruction,
    )
    return TIER2_FULL_SYSTEM, user


def format_reconcile_prompt(
    compressed_events: str,
    issues_list: str,
) -> tuple[str, str]:
    """Format reconciliation prompt pair (system, user)."""
    user = RECONCILE_USER.format(
        compressed_events=compressed_events,
        issues_list=issues_list,
    )
    return RECONCILE_SYSTEM, user


def format_issues_for_prompt(issues: list) -> str:
    """Format issues list for prompt input."""
    if not issues:
        return "None detected"

    lines = []
    for i, issue in enumerate[Issue](issues):
        if hasattr(issue, "root_cause"):
            lines.append(
                f"[{i+1}] {issue.severity.upper()} - Frequency: {issue.frequency} - Root Cause: {issue.root_cause}"
            )
        elif isinstance(issue, dict):
            lines.append(
                f"[{i+1}] {issue.get('severity', 'medium').upper()} - Frequency: {issue.get('frequency', 1)} - Root Cause: {issue.get('root_cause', 'Unknown')}"
            )
    return "\n".join(lines)
