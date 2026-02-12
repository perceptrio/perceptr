"""
Shared schema for session analysis output.
"""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class Issue(BaseModel):
    """An issue identified from the recording (matches video analyzer, with Issue fields)."""

    type: str = Field(
        description="rage_click | dead_click | navigation_loop | form_struggle | scroll_thrashing | unknown"
    )
    frequency: int = Field(
        description="Frequency of repeated action, e.g. clicks or visits", default=1
    )
    timestamp: str = Field(
        description="The timestamp of the finding in the recording. Format: MM:SS"
    )
    severity: str = Field(description="low | medium | high | critical")
    confidence: Optional[str] = Field(
        None, description="Confidence in this issue detection: high | medium | low"
    )
    root_cause: str = Field(
        description="The root cause and description of the finding. for example: when user received bad request error from network request, the button no longer works.",
    )
    reproduction_steps: str = Field(
        description="The steps to reproduce the finding. for example: click the button 3 times in a row.",
    )
    target: Optional[str] = Field(None, description="Element or URL involved")
    category: str = Field(
        description="The category of the finding. Can be one of: BUG, USABILITY_ISSUE, PERFORMANCE_ISSUE, ENHANCEMENT"
    )


class KeyEvent(BaseModel):
    """A key event in the recording at a specific timestamp (same shape as timestamp_descriptions)."""

    timestamp: str = Field(
        description="The timestamp of the event in the recording. Format: MM:SS"
    )
    description: str = Field(
        description="A short human-readable description of what happened at this moment."
    )


class TimestampInterval(BaseModel):
    """A timestamp interval in the recording."""

    start_time: str = Field(
        description="The start time of the interval in the recording. Format: MM:SS"
    )
    end_time: str = Field(
        description="The end time of the interval in the recording. Format: MM:SS"
    )
    short_title: str = Field(
        description="A short title summarizing the main activity or purpose of the interval."
    )
    issues: List[Issue] = Field(
        description="A list of issues identified during this interval.",
        default_factory=list,
    )
    key_events: List[KeyEvent] = Field(
        description="3-5 most significant events in this interval, each with timestamp (MM:SS) and description.",
        default_factory=list,
    )


class Tier1Result(BaseModel):
    """Tier 1 structured output: quick summary + enhanced findings + user action tags.

    Used when the session has minor issues and only a lightweight AI pass is needed.
    The AI refines programmatic findings and generates a human-readable summary.
    """

    summary: str = Field(
        description="2 sentence human-readable summary of what happened in the session. Be specific: mention elements, timestamps, and actions. Max 200 characters."
    )
    title: str = Field(
        description="Short title summarizing the main user task or session theme. Max 100 characters."
    )
    user_actions: List[str] = Field(
        description="User action tags (max 8). Examples: hesitant, confused, frustrated, exploring, onboarding, purchasing, form_filling, browsing, searching, stuck, blocked"
    )


class SessionAnalysisResult(BaseModel):
    """Result of analyzing normalized events (programmatic or AI)."""

    intervals: List[TimestampInterval] = Field(
        description="A list of logical intervals covering the entire recording."
    )
    summary: str = Field(
        description="A concise summary of the user's overall journey, key actions, observed emotional state (if discernible), main findings (issues/opportunities). in max 200 characters or less",
    )
    title: str = Field(
        description="A title for the recording analysis, summarizing the main user task or overall session theme. in max 100 characters or less"
    )

    health_score: float = Field(
        ge=0, le=100, description="Session health 0-100 (higher = healthier)"
    )
    confidence_score: float = Field(
        ge=0, le=1, description="Confidence in analysis 0-1"
    )
    user_actions: List[str] = Field(
        description="User action tags (max 8). Examples: hesitant, confused, frustrated, exploring, onboarding, purchasing, form_filling, browsing, searching, stuck, blocked"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": self.health_score,
            "confidence_score": self.confidence_score,
            "user_actions": self.user_actions,
            "intervals": [i.model_dump() for i in self.intervals],
            "summary": self.summary,
            "title": self.title,
        }
