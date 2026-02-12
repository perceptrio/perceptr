"""Node: extract keyframe screenshots from rrweb session (tier 2 only).

Renders the rrweb replay at key moments (navigations, form submits,
significant clicks) via Playwright and captures PNG screenshots.
These are base64-encoded and passed to the vision model.
"""

from __future__ import annotations

import tempfile

from graphs.session_analysis.state import SessionAnalysisState
from rrweb.keyframes import (
    extract_keyframes,
    get_keyframe_timestamps,
    load_keyframe_images_as_base64,
)


def extract_keyframes_node(state: SessionAnalysisState) -> dict:
    """Render rrweb replay at key moments and capture screenshots.

    Reads:  raw_session, normalized_events, max_frames
    Writes: keyframe_base64  (List of (timestamp_s, data_url))
    """
    raw_session = state["raw_session"]
    events = state["normalized_events"]
    max_frames = state.get("max_frames", 8)

    timestamps = get_keyframe_timestamps(events, max_frames=max_frames)
    keyframe_base64: list = []

    if timestamps and raw_session.get("data"):
        out_dir = tempfile.mkdtemp(prefix="rrweb_keyframes_")
        keyframe_paths = extract_keyframes(raw_session, timestamps, out_dir)
        keyframe_base64 = load_keyframe_images_as_base64(
            keyframe_paths, max_size_kb=400
        )

    return {"keyframe_base64": keyframe_base64}
