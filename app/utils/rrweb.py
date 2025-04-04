import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union, cast

# Import the constants from rrweb_consts
try:
    # Try relative import first (for when used as a module)
    from .rrweb_consts import (
        event_types,
        incremental_snapshot_event_source,
        media_interaction_types,
        mouse_interaction_types,
    )
except ImportError:
    # Fall back to absolute import (for when run as a script)
    # Use different variable names to avoid redefinition
    from rrweb_consts import event_types as event_types_imported
    from rrweb_consts import (
        incremental_snapshot_event_source as incremental_snapshot_event_source_imported,
    )
    from rrweb_consts import media_interaction_types as media_interaction_types_imported
    from rrweb_consts import mouse_interaction_types as mouse_interaction_types_imported

    # Then assign them to the desired variable names
    event_types = event_types_imported
    incremental_snapshot_event_source = incremental_snapshot_event_source_imported
    media_interaction_types = media_interaction_types_imported
    mouse_interaction_types = mouse_interaction_types_imported


class RRWebSessionUtils:
    def __init__(self, file_path: str):
        self.file_path = file_path

        # Try to load the session file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    self.session = json.load(f)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON: {e}")
                    # Check if it might be JSONL format
                    if str(e).startswith("Extra data:"):
                        print("Attempting to parse as JSONL format...")
                        f.seek(0)  # Reset file pointer to beginning
                        events = []
                        for line in f:
                            if line.strip():  # Skip empty lines
                                try:
                                    events.append(json.loads(line))
                                except json.JSONDecodeError:
                                    continue  # Skip invalid lines

                        if not events:
                            raise ValueError("Could not parse file as JSON or JSONL.")

                        # Create a session object from the events
                        self.session = {
                            "data": events,
                            "sessionId": f"jsonl_{os.path.basename(file_path)}",
                            "startTime": events[0].get("timestamp", 0) if events else 0,
                            "endTime": events[-1].get("timestamp", 0) if events else 0,
                            "userIdentity": {"id": "unknown"},
                        }
                    else:
                        raise
        except FileNotFoundError:
            raise ValueError(f"File not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Error loading session file: {str(e)}")

        self.events = self.session["data"]
        self.session_id = self.session["sessionId"]
        self.start_time = self.session["startTime"]
        self.end_time = self.session["endTime"]

        # Handle both integer timestamps and ISO string timestamps
        if isinstance(self.start_time, int) and isinstance(self.end_time, int):
            # If timestamps are Unix timestamps (integers)
            start_dt = datetime.fromtimestamp(
                self.start_time / 1000
            )  # Convert ms to seconds
            end_dt = datetime.fromtimestamp(self.end_time / 1000)
        else:
            # If timestamps are ISO strings
            start_dt = datetime.fromisoformat(self.start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(self.end_time.replace("Z", "+00:00"))

        self.duration = (end_dt - start_dt).total_seconds()

        if "userIdentity" in self.session:
            self.userIdentity = self.session["userIdentity"]
        else:
            self.userIdentity = None

    def get_events(self) -> List[Dict[str, Any]]:
        # Ensure the return type matches the annotation
        return cast(List[Dict[str, Any]], self.events)

    def get_session_id(self) -> str:
        # Ensure the return type matches the annotation
        return str(self.session_id)

    def get_session_summary(self) -> str:
        return f"""Session {self.session_id} lasted {self.get_duration()}
        and had {len(self.events)} events"""

    def get_user_identity(self) -> Dict[str, Any]:
        # Ensure the return type matches the annotation
        return cast(Dict[str, Any], self.userIdentity)

    def get_duration(self) -> str:
        seconds = self.duration
        hours = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

    def get_start_time(self) -> Union[str, int]:
        # The start time can be either a string or an integer
        if isinstance(self.start_time, str):
            return self.start_time
        return int(self.start_time)

    def get_end_time(self) -> Union[str, int]:
        # The end time can be either a string or an integer
        if isinstance(self.end_time, str):
            return self.end_time
        return int(self.end_time)

    def convert_events_to_video(
        self, output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        # Create events JSON file path in the same directory as the session file
        events_file_path = os.path.splitext(self.file_path)[0] + "_events.json"

        # Save events to a JSON file
        with open(events_file_path, "w", encoding="utf-8") as f:
            json.dump(self.events, f)

        # Get the output path
        if output_path is None:
            # Create output path based on input path
            input_path_without_ext = os.path.splitext(self.file_path)[0]
            output_path = f"{input_path_without_ext}_video.webm"

        try:
            # Run rrvideo CLI command with the events file
            cmd = ["rrvideo", "--input", events_file_path, "--output", output_path]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)

            # Check for success indicators in the output
            success_indicators = [
                "transformation completed",
                "successfully transformed",
            ]
            success = any(
                indicator in result.stdout.lower() for indicator in success_indicators
            )

            print(result.stdout)

            return {
                "success": success,
                "output_path": output_path,
                "events_file": events_file_path,
                "message": result.stdout,
            }

        except subprocess.CalledProcessError as e:
            error_message = f"Error creating video: {e}"
            if e.stderr:
                error_message += f"\n{e.stderr}"
            print(error_message)

            return {
                "success": False,
                "error": error_message,
                "events_file": events_file_path,
            }

    def convert_events_to_structured_json(self) -> List[Dict[str, Any]]:
        """
        Convert the raw RRWeb events into a structured JSON format.

        Returns:
            List[Dict[str, Any]]: A list of events with standardized fields
        """
        structured_events = []

        for event in self.events:
            # Extract timestamp and convert to hh:mm:ss
            timestamp_ms = event.get("timestamp", 0)
            timestamp_sec = timestamp_ms / 1000

            # Calculate time since start of session
            start_time_ms = self.start_time if isinstance(self.start_time, int) else 0
            elapsed_sec = (
                (timestamp_ms - start_time_ms) / 1000
                if start_time_ms > 0
                else timestamp_sec
            )

            # Format as hh:mm:ss
            hours = int(elapsed_sec // 3600)
            minutes = int((elapsed_sec % 3600) // 60)
            seconds = int(elapsed_sec % 60)
            timestamp_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            # Get event type
            event_type_id = event.get("type", -1)
            event_type = event_types.get(event_type_id, f"Unknown ({event_type_id})")

            # Create base structured event
            structured_event = {
                "timestamp": timestamp_str,
                "raw_timestamp": timestamp_ms,
                "event_type": event_type,
            }

            # Add specific data based on event type
            if event_type == "IncrementalSnapshot" and "data" in event:
                data = event["data"]
                source_id = data.get("source", -1)
                source = incremental_snapshot_event_source.get(
                    source_id, f"Unknown ({source_id})"
                )
                structured_event["incremental_snapshot_event_source"] = source

                # For mouse interactions, add the interaction type
                if source == "MouseInteraction" and "type" in data:
                    interaction_id = data.get("type", -1)
                    interaction = mouse_interaction_types.get(
                        interaction_id, f"Unknown ({interaction_id})"
                    )
                    structured_event["mouse_interaction_type"] = interaction

                    # Add mouse position if available
                    if "x" in data and "y" in data:
                        structured_event["position"] = {
                            "x": data.get("x"),
                            "y": data.get("y"),
                        }

                # For media interactions
                elif source == "MediaInteraction" and "type" in data:
                    interaction_id = data.get("type", -1)
                    interaction = media_interaction_types.get(
                        interaction_id, f"Unknown ({interaction_id})"
                    )
                    structured_event["media_interaction_type"] = interaction

                # For input events
                elif source == "Input" and "text" in data:
                    structured_event["input_data"] = {
                        "text": data.get("text"),
                        "isChecked": data.get("isChecked", False),
                    }

                # For scroll events
                elif source == "Scroll" and "x" in data and "y" in data:
                    structured_event["scroll_position"] = {
                        "x": data.get("x"),
                        "y": data.get("y"),
                    }

                # For mutation events, add detailed mutation information
                elif source == "Mutation":
                    mutation_summary = {
                        "adds": 0,
                        "removes": 0,
                        "texts": 0,
                        "attributes": 0,
                    }

                    # Count added nodes
                    if "adds" in data:
                        mutation_summary["adds"] = len(data.get("adds", []))

                    # Count removed nodes
                    if "removes" in data:
                        mutation_summary["removes"] = len(data.get("removes", []))

                    # Count text mutations
                    if "texts" in data:
                        mutation_summary["texts"] = len(data.get("texts", []))

                    # Count attribute mutations
                    if "attributes" in data:
                        mutation_summary["attributes"] = len(data.get("attributes", []))

                    structured_event["mutation_summary"] = mutation_summary

            # Add the structured event to our list
            structured_events.append(structured_event)

        return structured_events

    def save_structured_json(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Save the structured events to a JSON file.

        Args:
            output_path: Optional path for the output file.
                         If None, will use the original filename with
                         _structured.json suffix.

        Returns:
            Dict containing status and file path information
        """
        if output_path is None:
            output_path = os.path.splitext(self.file_path)[0] + "_structured.json"

        try:
            structured_events = self.convert_events_to_structured_json()

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(structured_events, f, indent=2)

            message = (
                f"Successfully saved {len(structured_events)} structured events "
                f"to {output_path}"
            )
            return {
                "success": True,
                "output_path": output_path,
                "event_count": len(structured_events),
                "message": message,
            }

        except Exception as e:
            error_message = f"Error saving structured JSON: {str(e)}"
            print(error_message)

            return {"success": False, "error": error_message}

    def filter_important_events(
        self, options: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter structured events to retain only the most important ones
        for session analysis.

        Args:
            options: Optional dict with filtering parameters:
                - keep_mouse_moves: Whether to keep mouse movement events
                  (default: False)
                - keep_focus_blur: Whether to keep focus/blur events (default: True)
                - keep_mouse_down_up: Whether to keep MouseDown and MouseUp events
                  (default: False)
                - keep_custom_events: Whether to keep Custom events (default: True)
                - scroll_sample_rate: Milliseconds between kept scroll events
                  (default: 1000)
                - mutation_threshold: Minimum elements affected to keep mutation
                  (default: 5)

        Returns:
            List of filtered structured events
        """
        # Default options
        if options is None:
            options = {}

        default_options = {
            "keep_mouse_moves": False,
            "keep_focus_blur": False,
            # By default, only keep clicks, not down/up events
            "keep_mouse_down_up": False,
            # By default, keep Custom events
            "keep_custom_events": False,
            # Keep 1 scroll event per second
            "scroll_sample_rate": 1000,
            # Min elements affected to keep mutation
            "mutation_threshold": 5,
        }

        # Update defaults with provided options
        for key, value in options.items():
            if key in default_options:
                default_options[key] = value

        options = default_options

        # Get structured events
        structured_events = self.convert_events_to_structured_json()
        important_events = []
        last_scroll_time = 0

        for event in structured_events:
            event_type = event.get("event_type")

            # Always keep these event types (DomContentLoaded, Load, FullSnapshot, Meta)
            if event_type in ["DomContentLoaded", "Load", "FullSnapshot", "Meta"]:
                important_events.append(event)
                continue

            # For incremental snapshots, filter by source
            if event_type == "IncrementalSnapshot":
                source = event.get("incremental_snapshot_event_source")

                # Keep important mouse interactions (clicks, context menu, etc.)
                if source == "MouseInteraction":
                    interaction_type = event.get("mouse_interaction_type")

                    # Handle Focus and Blur
                    if interaction_type in ["Focus", "Blur"]:
                        if options["keep_focus_blur"]:
                            important_events.append(event)

                    # Handle MouseDown and MouseUp
                    elif interaction_type in ["MouseDown", "MouseUp"]:
                        if options["keep_mouse_down_up"]:
                            important_events.append(event)

                    # Always keep clicks and other important mouse events
                    elif interaction_type in ["Click", "ContextMenu", "DblClick"]:
                        important_events.append(event)

                # Keep or discard mouse moves based on option
                elif source in ["MouseMove", "TouchMove", "Drag"]:
                    if options["keep_mouse_moves"]:
                        important_events.append(event)

                # Keep input events
                elif source == "Input":
                    important_events.append(event)

                # Sample scroll events
                elif source == "Scroll":
                    current_time = event.get("raw_timestamp", 0)
                    if current_time - last_scroll_time >= options["scroll_sample_rate"]:
                        important_events.append(event)
                        last_scroll_time = current_time

                # Keep viewport resize events
                elif source == "ViewportResize":
                    important_events.append(event)

                # Keep media interaction events
                elif source == "MediaInteraction":
                    important_events.append(event)

                # Filter mutation events to keep only significant ones
                elif source == "Mutation":
                    mutation_summary = event.get("mutation_summary", {})
                    mutation_score = (
                        mutation_summary.get("adds", 0)
                        + mutation_summary.get("removes", 0)
                        + mutation_summary.get("texts", 0)
                        + mutation_summary.get("attributes", 0)
                    )

                    if mutation_score >= options["mutation_threshold"]:
                        important_events.append(event)

            # Keep custom events based on option
            elif event_type == "Custom":
                if options["keep_custom_events"]:
                    important_events.append(event)

        return important_events

    def save_filtered_events(
        self,
        output_path: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Filter structured events to important ones and save them to a JSON file.

        Args:
            output_path: Optional path for the output file.
                         If None, will use the original filename with
                         _filtered.json suffix.
            options: Optional dict with filtering parameters
                    (see filter_important_events)

        Returns:
            Dict containing status and file path information
        """
        if output_path is None:
            output_path = os.path.splitext(self.file_path)[0] + "_filtered.json"

        try:
            filtered_events = self.filter_important_events(options)

            # Create a new session object with filtered events
            filtered_session = self.session.copy()
            filtered_session["data"] = filtered_events

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(filtered_session, f, indent=2)

            # Get original structured events count for comparison
            original_events = self.convert_events_to_structured_json()
            reduction = 100 - (len(filtered_events) / len(original_events) * 100)

            return {
                "success": True,
                "output_path": output_path,
                "original_event_count": len(original_events),
                "filtered_event_count": len(filtered_events),
                "reduction_percentage": f"{reduction:.2f}%",
                "message": (
                    f"Successfully filtered events from {len(original_events)} "
                    f"to {len(filtered_events)} ({reduction:.2f}% reduction)"
                ),
            }

        except Exception as e:
            error_message = f"Error saving filtered events: {str(e)}"
            print(error_message)

            return {"success": False, "error": error_message}

    def aggregate_events_by_second(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Aggregate all events by second into a single combined entry per second.

        Args:
            events: List of structured events to aggregate

        Returns:
            List of aggregated events - one per second with details of all events
        """
        if not events:
            return []

        # Group events by second
        events_by_second: Dict[str, List[Dict[str, Any]]] = {}

        for event in events:
            # Use the timestamp as the key for grouping
            timestamp = event.get("timestamp", "00:00:00")

            if timestamp not in events_by_second:
                events_by_second[timestamp] = []

            events_by_second[timestamp].append(event)

        # Convert to aggregated format - one entry per second
        aggregated_events = []

        for timestamp, second_events in events_by_second.items():
            # Sort events within this second by raw_timestamp
            second_events.sort(key=lambda x: x.get("raw_timestamp", 0))

            # Get earliest and latest raw timestamps for this second
            first_timestamp = second_events[0].get("raw_timestamp", 0)
            last_timestamp = second_events[-1].get("raw_timestamp", 0)

            # Create a summary of event types in this second
            event_type_counts: Dict[str, int] = {}
            for event in second_events:
                event_type = event.get("event_type")
                if event_type is not None:  # Ensure event_type is not None
                    if event_type not in event_type_counts:
                        event_type_counts[event_type] = 0
                    event_type_counts[event_type] += 1

            # Process Mutation events for an overall summary
            mutation_summary = {"adds": 0, "removes": 0, "texts": 0, "attributes": 0}

            for event in second_events:
                if (
                    event.get("event_type") == "IncrementalSnapshot"
                    and event.get("incremental_snapshot_event_source") == "Mutation"
                    and "mutation_summary" in event
                ):
                    summary = event["mutation_summary"]
                    mutation_summary["adds"] += summary.get("adds", 0)
                    mutation_summary["removes"] += summary.get("removes", 0)
                    mutation_summary["texts"] += summary.get("texts", 0)
                    mutation_summary["attributes"] += summary.get("attributes", 0)

            # Collect all interaction types in this second
            interactions = []
            for event in second_events:
                if (
                    event.get("event_type") == "IncrementalSnapshot"
                    and event.get("incremental_snapshot_event_source")
                    == "MouseInteraction"
                ):
                    interaction_type = event.get("mouse_interaction_type")
                    position = event.get("position")

                    if interaction_type and interaction_type not in [
                        "MouseMove",
                        "TouchMove",
                    ]:
                        interaction_info = {"type": interaction_type}
                        if position:
                            interaction_info["position"] = position

                        interactions.append(interaction_info)

            # Collect all input events - ensure they're dictionaries
            inputs: List[Dict[str, Any]] = []
            for event in second_events:
                if (
                    event.get("event_type") == "IncrementalSnapshot"
                    and event.get("incremental_snapshot_event_source") == "Input"
                    and "input_data" in event
                ):
                    input_data = event.get("input_data")
                    if isinstance(input_data, dict):
                        inputs.append(input_data)

            # Get last scroll position
            last_scroll = None
            for event in reversed(second_events):
                if (
                    event.get("event_type") == "IncrementalSnapshot"
                    and event.get("incremental_snapshot_event_source") == "Scroll"
                    and "scroll_position" in event
                ):
                    last_scroll = event.get("scroll_position")
                    break

            # Generate a one-line summary of the second
            summary = self._generate_second_summary(
                second_events, event_type_counts, mutation_summary, interactions, inputs
            )

            # Create the aggregated event for this second
            aggregated_event = {
                "timestamp": timestamp,
                "raw_timestamp_start": first_timestamp,
                "raw_timestamp_end": last_timestamp,
                "summary": summary,
                "event_count": len(second_events),
                "event_types": event_type_counts,
                "events": second_events,  # Include all original events
            }

            # Add aggregated data if present
            if sum(mutation_summary.values()) > 0:
                aggregated_event["mutation_summary"] = mutation_summary

            if interactions:
                aggregated_event["interactions"] = interactions

            if inputs:
                aggregated_event["inputs"] = inputs

            if last_scroll:
                aggregated_event["final_scroll"] = last_scroll

            aggregated_events.append(aggregated_event)

        # Sort by timestamp
        aggregated_events.sort(key=lambda x: x.get("raw_timestamp_start", 0))

        return aggregated_events

    def _generate_second_summary(
        self,
        events: List[Dict[str, Any]],
        event_type_counts: Dict[str, int],
        mutation_summary: Dict[str, int],
        interactions: List[Dict[str, Any]],
        inputs: List[Dict[str, Any]],
    ) -> str:
        """
        Generate a concise but comprehensive one-line summary of what happened
        in this second.

        Returns:
            str: A human-readable summary of the main activities
        """
        summary_parts = []

        # Check for key page events
        if "FullSnapshot" in event_type_counts:
            summary_parts.append("Page snapshot")

        if "Meta" in event_type_counts:
            summary_parts.append("Metadata")

        # Process user interactions
        if interactions:
            interaction_types: Set[str] = set(
                interaction.get("type", "") for interaction in interactions
            )
            interaction_summary = []

            # Check for significant interactions
            if "Click" in interaction_types:
                interaction_summary.append("click")
            if "DblClick" in interaction_types:
                interaction_summary.append("double-click")
            if "ContextMenu" in interaction_types:
                interaction_summary.append("right-click")
            if "Focus" in interaction_types:
                interaction_summary.append("focus")
            if "Blur" in interaction_types:
                interaction_summary.append("blur")

            # Add other interaction types if present
            other_types = interaction_types - {
                "Click",
                "DblClick",
                "ContextMenu",
                "Focus",
                "Blur",
                "MouseMove",
                "TouchMove",
            }
            for interaction_type in other_types:
                interaction_summary.append(interaction_type.lower())

            if interaction_summary:
                summary_parts.append(f"User {'/'.join(interaction_summary)}")

        # Process input events
        if inputs:
            has_text = any(input_data.get("text", "") for input_data in inputs)
            if has_text:
                # Get first non-empty text
                for input_data in inputs:
                    text = input_data.get("text", "")
                    if text:
                        if len(text) > 15:
                            text = text[:12] + "..."
                        summary_parts.append(f"Input '{text}'")
                        break
            else:
                summary_parts.append("Input interaction")

        # Check for custom events
        if "Custom" in event_type_counts:
            summary_parts.append("Custom event")

        # Process DOM mutations
        mutation_total = sum(mutation_summary.values())
        if mutation_total > 0:
            # Determine if this is a major DOM update
            if mutation_total > 50:
                summary_parts.append(f"Major DOM update ({mutation_total} changes)")
            else:
                mutation_details = []
                if mutation_summary.get("adds", 0) > 0:
                    mutation_details.append(f"{mutation_summary['adds']} adds")
                if mutation_summary.get("removes", 0) > 0:
                    mutation_details.append(f"{mutation_summary['removes']} removes")
                if mutation_summary.get("texts", 0) > 0:
                    mutation_details.append(f"{mutation_summary['texts']} texts")
                if mutation_summary.get("attributes", 0) > 0:
                    mutation_details.append(f"{mutation_summary['attributes']} attrs")

                # Format based on number of mutation types
                if len(mutation_details) > 2:
                    summary_parts.append(f"DOM: {mutation_total} changes")
                else:
                    summary_parts.append(f"DOM: {', '.join(mutation_details)}")

        # Check for scrolling
        has_scroll = any(
            e.get("incremental_snapshot_event_source") == "Scroll"
            for e in events
            if e.get("event_type") == "IncrementalSnapshot"
        )
        if has_scroll:
            summary_parts.append("Scroll")

        # Check for mouse movement (only add if no other significant events)
        has_mouse_move = any(
            e.get("incremental_snapshot_event_source") == "MouseMove"
            for e in events
            if e.get("event_type") == "IncrementalSnapshot"
        )
        if has_mouse_move and not summary_parts:
            summary_parts.append("Mouse movement")

        # If nothing specific found
        if not summary_parts:
            if len(event_type_counts) > 0:
                main_event_type = max(event_type_counts.items(), key=lambda x: x[1])[0]
                return f"{main_event_type} events"
            return "No significant activity"

        # Join all parts with separator
        return " | ".join(summary_parts)

    def _find_interaction_target(
        self, events: List[Dict[str, Any]], interaction: Dict[str, Any]
    ) -> str:
        """
        Try to find a description of the target element for an interaction.
        This is a best-effort function that looks for clues in surrounding events.

        Returns:
            str: A short description of the target element, or empty string if not found
        """
        # This is a simplified implementation - in a real implementation,
        # you would need to correlate the target ID with DOM elements
        # from FullSnapshot events or other events to get accurate element info

        # Look for element attributes in nearby mutation events that might
        # indicate what was clicked (like class changes for active states)
        for event in events:
            if (
                event.get("event_type") == "IncrementalSnapshot"
                and event.get("incremental_snapshot_event_source") == "Input"
            ):
                return "input field"

        # Check for common UI element interactions
        pos = interaction.get("position", {})
        if pos and isinstance(pos, dict):
            # Ensure x and y are properly accessed with default values
            x = pos.get("x", 0)
            y = pos.get("y", 0)

            # Only proceed if values are numerical
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                if 0 <= x <= 200 and 0 <= y <= 200:
                    return "navigation element"  # Common location for nav elements
                elif x >= 0 and y <= 100:
                    return "header element"

        # Default - we don't have enough info
        return ""

    def save_aggregated_events(
        self,
        filtered_events: Optional[List[Dict[str, Any]]] = None,
        output_path: Optional[str] = None,
        filter_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Filter events and save them with combined second-based aggregation.

        Args:
            filtered_events: Optional pre-filtered events. If None, will filter using
                filter_options.
            output_path: Path to save the aggregated events. If None, will use original
                filename with _aggregated.json suffix.
            filter_options: Options for filtering if filtered_events is not provided.

        Returns:
            Dict containing status and file path information
        """
        if output_path is None:
            output_path = os.path.splitext(self.file_path)[0] + "_aggregated.json"

        try:
            # Get filtered events if not provided
            if filtered_events is None:
                filtered_events = self.filter_important_events(filter_options)

            # Aggregate events
            aggregated_events = self.aggregate_events_by_second(filtered_events)

            # Create a new session object with aggregated events
            aggregated_session = self.session.copy()
            aggregated_session["data"] = aggregated_events

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(aggregated_session, f, indent=2)

            # Calculate reduction percentages
            original_events = self.convert_events_to_structured_json()
            reduction_from_original = 100 - (
                len(aggregated_events) / len(original_events) * 100
            )
            reduction_from_filtered = (
                100 - (len(aggregated_events) / len(filtered_events) * 100)
                if filtered_events
                else 0
            )

            message = (
                f"Successfully aggregated events to {len(aggregated_events)} seconds "
                f"(down from {len(filtered_events) if filtered_events else 0} "
                f"filtered events)"
            )
            return {
                "success": True,
                "output_path": output_path,
                "original_event_count": len(original_events),
                "filtered_event_count": len(filtered_events) if filtered_events else 0,
                "aggregated_event_count": len(aggregated_events),
                "reduction_from_original": f"{reduction_from_original:.2f}%",
                "reduction_from_filtered": f"{reduction_from_filtered:.2f}%",
                "message": message,
            }

        except Exception as e:
            error_message = f"Error saving aggregated events: {str(e)}"
            print(error_message)

            return {"success": False, "error": error_message}

    def process_events(
        self,
        filter_options: Optional[Dict[str, Any]] = None,
        save_events: bool = False,
    ) -> Dict[str, Any]:
        """
        Process raw events by filtering important events and aggregating them by second.

        This is a convenience method that combines filtering and aggregation steps
        in one call.

        Args:
            filter_options: Optional dict with filtering parameters
                (same as filter_important_events)
            save_events: If True, save the aggregated events to a file named
                `agg_events.json` in the same directory as the input file.

        Returns:
            Dict containing:
                - success: Boolean indicating if the operation was successful
                - filtered_events: List of filtered events
                - aggregated_events: List of aggregated events (one per second)
                - stats: Dictionary with statistics about the processing
                - output_path: Path where aggregated events were saved (if provided)
                - save_success: Boolean indicating if saving was successful (if path provided)
                - save_error: Error message if saving failed (if path provided)
        """
        result: Dict[str, Any] = {"success": False}  # Initialize result dict

        try:
            # Step 1: Get structured events
            structured_events = self.convert_events_to_structured_json()

            # Step 2: Filter events
            filtered_events = self.filter_important_events(filter_options)

            # Step 3: Aggregate events
            aggregated_events = self.aggregate_events_by_second(filtered_events)

            # Calculate statistics
            reduction_from_original = (
                100 - (len(filtered_events) / len(structured_events) * 100)
                if structured_events
                else 0
            )
            reduction_to_aggregated = (
                100 - (len(aggregated_events) / len(filtered_events) * 100)
                if filtered_events
                else 0
            )
            total_reduction = (
                100 - (len(aggregated_events) / len(structured_events) * 100)
                if structured_events
                else 0
            )

            stats = {
                "original_event_count": len(structured_events),
                "filtered_event_count": len(filtered_events),
                "aggregated_event_count": len(aggregated_events),
                "filtering_reduction": f"{reduction_from_original:.2f}%",
                "aggregation_reduction": f"{reduction_to_aggregated:.2f}%",
                "total_reduction": f"{total_reduction:.2f}%",
            }

            # Include filter options used in stats
            if filter_options:
                stats["filter_options"] = filter_options

            result = {
                "success": True,
                "filtered_events": filtered_events,
                "aggregated_events": aggregated_events,
                "stats": stats,
            }

            # Step 4: Save aggregated events if save_events is True
            if save_events:
                # Determine output path based on input file path
                input_dir = os.path.dirname(self.file_path)
                output_path = os.path.join(input_dir, "agg_events.json")

                result["output_path"] = output_path
                try:
                    # Create a session object structure for saving
                    aggregated_session = self.session.copy()
                    aggregated_session["data"] = aggregated_events

                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(aggregated_session, f, indent=2)

                    result["save_success"] = True
                    print(f"Aggregated events successfully saved to {output_path}")

                except Exception as save_e:
                    save_error_message = (
                        f"Error saving aggregated events: {str(save_e)}"
                    )
                    print(save_error_message)
                    result["save_success"] = False
                    result["save_error"] = save_error_message
                    # Keep overall success as True since processing succeeded
                    # but add save error info.

            return result

        except Exception as e:
            error_message = f"Error processing events: {str(e)}"
            print(error_message)

            return {"success": False, "error": error_message}


if __name__ == "__main__":
    try:
        # Example file path - replace with your actual file path
        file_path = "recordings/web-sdk/1.json"

        # Initialize session utils
        session = RRWebSessionUtils(file_path)

        # Print session summary
        print(session.get_session_summary())
        print(f"Start time: {session.get_start_time()}")
        print(f"End time: {session.get_end_time()}")
        print(f"Duration: {session.get_duration()}")
        print(f"Events: {len(session.get_events())}")
        print(f"User identity: {session.get_user_identity()}")

        # # Convert to structured JSON
        # print("\nConverting session to structured JSON...")
        # output_path = os.path.splitext(file_path)[0] + "_structured.json"
        # result = session.save_structured_json(output_path)
        # print(result)

        # # Filter events to important ones
        # print("\nFiltering session events...")

        # # Filter with custom options
        # filter_options = {
        #     'keep_focus_blur': False,
        #     'keep_mouse_down_up': False,  # Exclude MouseDown and MouseUp events
        #     'keep_custom_events': False,   # Exclude Custom events
        #     'mutation_threshold': 3,      # More permissive for mutations
        #     'scroll_sample_rate': 2000    # More aggressive scroll filtering
        # }
        # filtered_output_path = os.path.splitext(file_path)[0] + "_filtered.json"
        # result_filtered = session.save_filtered_events(
        #    filtered_output_path, filter_options
        # )
        # if result_filtered["success"]:
        #     print(f"\nFiltering successful!")
        #     print(f"Filtered events saved to: {result_filtered['output_path']}")
        #     print(f"Original events: {result_filtered['original_event_count']}")
        #     print(f"Filtered events: {result_filtered['filtered_event_count']}")
        #     print(f"Reduction: {result_filtered['reduction_percentage']}")
        #     print(f"Filter options: {filter_options}")

        #     # Create time-based aggregation (one entry per second with
        #     # events and summaries)
        #     print("\nAggregating events by second...")
        #     aggregated_output_path = (
        #         os.path.splitext(file_path)[0] + "_aggregated.json"
        #     )
        #     # Use the already filtered events to avoid filtering again
        #     with open(result_filtered["output_path"], "r", encoding="utf-8") as f:
        #         filtered_session = json.load(f)
        #         filtered_events = filtered_session["data"]

        #     result_aggregated = session.save_aggregated_events(
        #         filtered_events=filtered_events,
        #         output_path=aggregated_output_path
        #     )

        #     if result_aggregated["success"]:
        #         print(f"\nAggregation successful!")
        #         print(
        #             f"Aggregated events saved to: {result_aggregated['output_path']}"
        #         )
        #         print(f"Original events: {result_aggregated['original_event_count']}")
        #         print(f"Filtered events: {result_aggregated['filtered_event_count']}")
        #         print(
        #             f"Aggregated events: "
        #             f"{result_aggregated['aggregated_event_count']}"
        #         )
        #         print(
        #             f"Reduction from original: "
        #             f"{result_aggregated['reduction_from_original']}"
        #         )
        #         print(
        #             f"Reduction from filtered: "
        #             f"{result_aggregated['reduction_from_filtered']}"
        #         )
        #     else:
        #         print("\nAggregation failed!")
        #         print(f"Error: {result_aggregated['error']}")
        # else:
        #     print("\nFiltering failed!")
        #     print(f"Error: {result_filtered['error']}")

        print("Processing events...")
        processed_events = session.process_events()
        print(processed_events["stats"])

        # Convert to video
        print("\nConverting session to video...")
        result = session.convert_events_to_video()

        if result["success"]:
            print("\nVideo conversion successful!")
            print(f"Video saved to: {result['output_path']}")
        else:
            print("\nVideo conversion failed!")
            if "error" in result:
                print(f"Error: {result['error']}")
            else:
                print(f"Message: {result['message']}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
