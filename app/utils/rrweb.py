import gzip
from datetime import datetime
import json
from decimal import Decimal
from typing import Dict, List, Optional
import ijson
import os
from pathlib import Path


event_types = {
    -1: "Unknown",
    1: "Load",
    2: "FullSnapshot",
    3: "IncrementalSnapshot",
    4: "Meta",
    5: "Custom",
    6: "Plugin",
}

incremental_snapshot_event_source = {
    0: "Mutation",
    1: "MouseMove",
    2: "MouseInteraction",
    3: "Scroll",
    4: "ViewportResize",
    5: "Input",
    6: "TouchMove",
    7: "MediaInteraction",
    8: "StyleSheetRule",
    9: "CanvasMutation",
    10: "Font",
    11: "Log",
    12: "Drag",
    13: "StyleDeclaration",
    14: "Selection",
    15: "AdoptedStyleSheet",
}

mouse_interaction_types = {
    0: "mouseup",
    1: "mousedown",
    2: "click",
    3: "contextmenu",
    4: "dblclick",
    5: "focus",
    6: "blur",
    7: "touchstart",
    8: "touchend",
    9: "touchcancel",
    10: "touchmove",
}

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def maybe_decompress(x: str | dict| None) -> dict|None:
    if x is None:
        return None
    if isinstance(x, str):
        # Decode the decompressed bytes to a UTF-8 string
        decompressed_str = gzip.decompress(x.encode("latin-1")).decode("utf-8")
        # Parse the JSON string
        return json.loads(decompressed_str)
    return x


def calculate_movement_direction(start_x: int, start_y: int, end_x: int, end_y: int) -> str:
    """Calculate the direction of movement between two points using 8 cardinal directions.
    
    Args:
        start_x: Starting X coordinate
        start_y: Starting Y coordinate
        end_x: Ending X coordinate
        end_y: Ending Y coordinate
        
    Returns:
        String describing the movement direction
    """
    dx = end_x - start_x
    dy = end_y - start_y
    
    # Use a small threshold to avoid detecting tiny movements
    threshold = 3
    if abs(dx) < threshold and abs(dy) < threshold:
        return "stationary"
    
    # Calculate the primary direction based on the larger movement
    if abs(dx) > abs(dy) * 2:
        return "right" if dx > 0 else "left"
    elif abs(dy) > abs(dx) * 2:
        return "down" if dy > 0 else "up"
    else:
        # Diagonal movement
        if dx > 0:
            return "up-right" if dy < 0 else "down-right"
        else:
            return "up-left" if dy < 0 else "down-left"


def analyze_mouse_movement(positions: List[dict]) -> dict:
    """Analyze a sequence of mouse movements to extract patterns and directions.
    
    Args:
        positions: List of position records with x, y coordinates and timeOffset
        
    Returns:
        Dictionary containing movement analysis
    """
    if not positions or len(positions) < 2:
        return {"movement_pattern": "single_point"}
    
    movements = []
    total_distance = 0
    duration = positions[-1]["timeOffset"] - positions[0]["timeOffset"]
    
    for i in range(len(positions) - 1):
        start = positions[i]
        end = positions[i + 1]
        
        # Calculate direction
        direction = calculate_movement_direction(start["x"], start["y"], end["x"], end["y"])
        
        # Calculate distance
        dx = end["x"] - start["x"]
        dy = end["y"] - start["y"]
        distance = (dx * dx + dy * dy) ** 0.5
        
        # Calculate time between points
        time_diff = end["timeOffset"] - start["timeOffset"]
        
        movements.append({
            "direction": direction,
            "distance": round(distance, 2),
            "duration_ms": time_diff,
            "speed": round(distance / time_diff, 2) if time_diff != 0 else 0
        })
        
        total_distance += distance
    
    # Analyze the movement pattern
    primary_directions = [m["direction"] for m in movements]
    
    # Determine if the movement is mostly in one direction
    direction_counts = {}
    for direction in primary_directions:
        direction_counts[direction] = direction_counts.get(direction, 0) + 1
    
    most_common_direction = max(direction_counts.items(), key=lambda x: x[1])
    is_consistent = most_common_direction[1] > len(movements) * 0.6
    
    return {
        "movements": movements,
        "total_distance": round(total_distance, 2),
        "duration_ms": duration,
        "average_speed": round(total_distance / duration, 2) if duration != 0 else 0,
        "movement_pattern": {
            "primary_direction": most_common_direction[0] if is_consistent else "mixed",
            "is_consistent": is_consistent,
            "direction_changes": len([i for i in range(len(primary_directions)-1) 
                                   if primary_directions[i] != primary_directions[i+1]])
        }
    }


def calculate_scroll_direction(start_x: int, start_y: int, end_x: int, end_y: int) -> str:
    """Calculate the direction of scrolling between two positions.
    
    Args:
        start_x: Starting X scroll position
        start_y: Starting Y scroll position
        end_x: Ending X scroll position
        end_y: Ending Y scroll position
        
    Returns:
        String describing the scroll direction
    """
    dx = end_x - start_x
    dy = end_y - start_y
    
    # Use a small threshold to avoid detecting tiny scrolls
    threshold = 3
    if abs(dx) < threshold and abs(dy) < threshold:
        return "stationary"
    
    # Calculate the primary direction based on the larger movement
    if abs(dx) > abs(dy) * 2:
        return "right" if dx > 0 else "left"
    elif abs(dy) > abs(dx) * 2:
        return "down" if dy > 0 else "up"
    else:
        # Diagonal scrolling
        if dx > 0:
            return "up-right" if dy < 0 else "down-right"
        else:
            return "up-left" if dy < 0 else "down-left"


def analyze_scroll_movement(current_pos: dict, prev_pos: dict) -> dict:
    """Analyze scroll movement to extract patterns and directions.
    
    Args:
        current_pos: Current scroll position with x, y coordinates
        prev_pos: Previous scroll position with x, y coordinates
        
    Returns:
        Dictionary containing scroll analysis
    """
    
    # Calculate direction
    direction = calculate_scroll_direction(
        prev_pos.get("x", 0), prev_pos.get("y", 0),
        current_pos.get("x", 0), current_pos.get("y", 0)
    )
    
    # Calculate distance
    dx = current_pos.get("x", 0) - prev_pos.get("x", 0)
    dy = current_pos.get("y", 0) - prev_pos.get("y", 0)
    distance = (dx * dx + dy * dy) ** 0.5
    
    return {
        "direction": direction,
        "distance": round(distance, 2),
        "position": {"x": current_pos.get("x", 0), "y": current_pos.get("y", 0)},
        "delta": {"x": dx, "y": dy}
    }


def count_event_categories(events: list) -> dict:
    """Count events by category.
    
    Args:
        events: List of enhanced events
        
    Returns:
        Dictionary mapping categories to counts
    """
    category_counts = {}
    for event in events:
        # Use event type instead of category since category has been removed
        event_type = event.get("type", "Uncategorized")
        category_counts[event_type] = category_counts.get(event_type, 0) + 1
    return category_counts


def get_session_duration(events: list) -> str:
    """Calculate the total session duration.
    
    Args:
        events: List of events
        
    Returns:
        Duration string in MM:SS format
    """
    if not events or len(events) < 2:
        return "00:00"
    
    first_timestamp = events[0]["timestamp"]
    last_timestamp = events[-1]["timestamp"]
    
    return calculate_duration(first_timestamp, last_timestamp)


def calculate_duration(start_timestamp: str, end_timestamp: str) -> str:
    """Calculate duration between two timestamps.
    
    Args:
        start_timestamp: Starting timestamp in MM:SS format
        end_timestamp: Ending timestamp in MM:SS format
        
    Returns:
        Duration string in MM:SS format
    """
    start_time = parse_timestamp(start_timestamp)
    end_time = parse_timestamp(end_timestamp)
    
    duration_seconds = end_time - start_time
    minutes = duration_seconds // 60
    seconds = duration_seconds % 60
    
    return f"{int(minutes):02d}:{int(seconds):02d}"


def parse_timestamp(timestamp: str) -> int:
    """Parse a timestamp string into seconds.
    
    Args:
        timestamp: Timestamp string in MM:SS format
        
    Returns:
        Total seconds
    """
    parts = timestamp.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


def summarize_mouse_movements(positions: list) -> dict:
    """Summarize a sequence of mouse movement positions.
    
    Args:
        positions: List of position records with x, y coordinates and event_timestamp
        
    Returns:
        Dictionary containing the summary
    """
    if not positions or len(positions) < 2:
        return None
    
    # Get timestamps
    start_timestamp = positions[0].get("event_timestamp", "00:00")
    end_timestamp = positions[-1].get("event_timestamp", "00:00")
    
    # Extract coordinates for analysis
    coords = []
    for pos in positions:
        coords.append({
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "timeOffset": pos.get("timeOffset", 0)
        })
    
    # Use the existing analysis function
    movement_analysis = analyze_mouse_movement(coords)
    
    return {
        "timestamp": start_timestamp,
        "type": "Mouse Movement",
        "details": {
            "duration": calculate_duration(start_timestamp, end_timestamp),
            "movement_pattern": movement_analysis.get("movement_pattern", "unknown"),
            "total_distance": movement_analysis.get("total_distance", 0),
            "average_speed": movement_analysis.get("average_speed", 0)
        }
    }


def summarize_scroll_sequence(scroll_events: list) -> dict:
    """Summarize a sequence of scroll events.
    
    Args:
        scroll_events: List of scroll event records
        
    Returns:
        Dictionary containing the summary
    """
    if not scroll_events or len(scroll_events) < 2:
        return None
    
    # Get timestamps
    start_timestamp = scroll_events[0].get("timestamp", "00:00")
    end_timestamp = scroll_events[-1].get("timestamp", "00:00")
    
    # Calculate total vertical and horizontal scrolling
    total_y = 0
    total_x = 0
    directions = []
    
    for i in range(1, len(scroll_events)):
        prev_pos = {"x": scroll_events[i-1].get("x", 0), "y": scroll_events[i-1].get("y", 0)}
        curr_pos = {"x": scroll_events[i].get("x", 0), "y": scroll_events[i].get("y", 0)}
        
        # Calculate direction and distance
        scroll_analysis = analyze_scroll_movement(curr_pos, prev_pos)
        
        total_y += abs(scroll_analysis.get("delta", {}).get("y", 0))
        total_x += abs(scroll_analysis.get("delta", {}).get("x", 0))
        directions.append(scroll_analysis.get("direction", "unknown"))
    
    # Determine primary direction
    direction_pattern = "mixed"
    if total_y > total_x * 3:
        direction_pattern = "primarily vertical"
    elif total_x > total_y * 3:
        direction_pattern = "primarily horizontal"
    
    return {
        "timestamp": start_timestamp,
        "type": "Scrolling Activity",
        "details": {
            "duration": calculate_duration(start_timestamp, end_timestamp),
            "scroll_pattern": direction_pattern,
            "total_distance": round(total_y + total_x, 2),
            "vertical_distance": round(total_y, 2),
            "horizontal_distance": round(total_x, 2),
            "scroll_count": len(scroll_events)
        }
    }


def summarize_console_logs(logs: list) -> dict:
    """Summarize a sequence of console logs.
    
    Args:
        logs: List of console log records
        
    Returns:
        Dictionary containing the summary
    """
    if not logs:
        return None
    
    # Get timestamps
    timestamp = logs[0].get("timestamp", "00:00")
    
    # Group by log type and message pattern
    grouped_logs = {}
    message_counts = {}
    
    for log in logs:
        level = log.get("level", "unknown")
        message = log.get("message", "")
        
        # Create a simplified message key for grouping similar messages
        message_key = str(message)
        if isinstance(message, list) and len(message) > 0:
            # For list messages, use just the first part as the key (usually the pattern)
            message_key = str(message[0])
        
        group_key = f"{level}:{message_key}"
        
        if group_key not in message_counts:
            message_counts[group_key] = 0
            if level not in grouped_logs:
                grouped_logs[level] = []
            
            # Only add new unique messages to the group
            if message and not any(str(m) == str(message) for m in grouped_logs[level]):
                grouped_logs[level].append(message)
        
        message_counts[group_key] += 1
    
    # Count total messages by level
    level_counts = {}
    for group_key, count in message_counts.items():
        level = group_key.split(":", 1)[0]
        level_counts[level] = level_counts.get(level, 0) + count
    
    return {
        "timestamp": timestamp,
        "type": "Console Logs",
        "details": {
            "log_count": len(logs),
            "grouped_by_level": level_counts,
            "sample_messages": {
                level: messages[:2] for level, messages in grouped_logs.items()
            },
            "message_pattern_count": len(message_counts)
        }
    }


def aggregate_similar_events(events: list) -> list:
    """Aggregate similar events like consecutive input changes to the same field and console logs with the same pattern.
    
    Args:
        events: List of processed events to aggregate
        
    Returns:
        List of aggregated events
    """
    # Sort events by timestamp
    events.sort(key=lambda x: parse_timestamp(x["timestamp"]))
    
    # First pass: Process console logs
    first_pass_events = []
    console_logs_by_pattern = {}
    
    for event in events:
        # If this is a console log event
        if event["type"] == "Console Logs":
            # Create a unique key based on the log pattern
            log_pattern = ""
            sample_messages = event["details"].get("sample_messages", {})
            
            # Extract the first message pattern as the key
            for level, messages in sample_messages.items():
                if messages and len(messages) > 0:
                    # Use the first part of the first message as the pattern
                    if isinstance(messages[0], list) and len(messages[0]) > 0:
                        log_pattern = str(messages[0][0])
                    else:
                        log_pattern = str(messages[0])
                    break
            
            # Create a unique key for this console log pattern
            unique_key = f"console:{log_pattern}"
            
            # If we've seen this pattern before, update the existing event
            if unique_key in console_logs_by_pattern:
                existing_event_index = console_logs_by_pattern[unique_key]
                existing_event = first_pass_events[existing_event_index]
                
                # Update timestamp
                first_pass_events[existing_event_index]["timestamp"] = event["timestamp"]
                
                # Combine log counts
                existing_log_count = existing_event["details"].get("log_count", 0)
                new_log_count = event["details"].get("log_count", 0)
                first_pass_events[existing_event_index]["details"]["log_count"] = existing_log_count + new_log_count
                
                # Combine grouped_by_level counts
                existing_levels = existing_event["details"].get("grouped_by_level", {})
                new_levels = event["details"].get("grouped_by_level", {})
                
                for level, count in new_levels.items():
                    if level in existing_levels:
                        existing_levels[level] += count
                    else:
                        existing_levels[level] = count
                
                first_pass_events[existing_event_index]["details"]["grouped_by_level"] = existing_levels
            else:
                # Add this event to our aggregated list
                first_pass_events.append(event)
                # Store its index for future reference
                console_logs_by_pattern[unique_key] = len(first_pass_events) - 1
        else:
            # For all other events, just add them directly
            first_pass_events.append(event)
    
    # Second pass: Identify and aggregate consecutive input events
    final_events = []
    
    # Group events by timestamp to identify consecutive events
    i = 0
    while i < len(first_pass_events):
        current_event = first_pass_events[i]
        
        # If this is an input event, check for consecutive inputs on the same element
        if current_event["type"] == "Input changed":
            current_element = current_event["details"]["element"]
            current_value_type = current_event["details"].get("value_type")
            
            # Look ahead for consecutive input events on the same element
            j = i + 1
            last_input_index = i  # Start with current event as the last one
            
            while j < len(first_pass_events):
                next_event = first_pass_events[j]
                
                # If the next event is also an input event on the same element
                if (next_event["type"] == "Input changed" and
                    next_event["details"]["element"] == current_element and
                    next_event["details"].get("value_type") == current_value_type):
                    # Update the last input index
                    last_input_index = j
                    j += 1
                else:
                    # Break if we encounter a different event type or different element
                    break
            
            # Add only the last input event for this element
            if last_input_index > i:
                # Add a flag to indicate this is an aggregated input event
                last_event = first_pass_events[last_input_index]
                last_event["details"]["is_aggregated"] = True
                last_event["details"]["aggregated_count"] = last_input_index - i + 1
                final_events.append(last_event)
                
                # Skip all the intermediate input events
                i = last_input_index + 1
            else:
                # This is a single input event, add it as is
                current_event["details"]["is_aggregated"] = False
                current_event["details"]["aggregated_count"] = 1
                final_events.append(current_event)
                i += 1
        else:
            # For non-input events, add them directly
            final_events.append(current_event)
            i += 1
    
    # Sort the final list by timestamp
    final_events.sort(key=lambda x: parse_timestamp(x["timestamp"]))
    return final_events


def summarize_for_llm(file_path: str, output_file: Optional[str] = None) -> dict:
    """Streamlined function to analyze rrweb recordings and produce LLM-friendly summaries.
    
    This function focuses solely on extracting user behaviors in a format that's
    easy for an LLM to understand and generate insights from. It eliminates the complex
    node tracking and focuses on high-level user interactions.
    
    Args:
        file_path: Path to the rrweb JSON recording file
        output_file: Optional path to save the results
        
    Returns:
        Dictionary with summarized events and metadata
    """
    with open(file_path, "r") as file:
        # Extract events
        events = []
        start_timestamp = None
        
        for list_of_snapshots in ijson.items(file, "data.snapshots"):
            if list_of_snapshots:
                if start_timestamp is None:
                    start_timestamp = list_of_snapshots[0]["timestamp"]
                events.extend(list_of_snapshots)
    
    if not events:
        return {"error": "No events found in the recording file"}
    
    # Process events to extract user-focused information
    processed_events = []
    temp_values = {}
    mouse_positions_buffer = []
    scroll_events_buffer = []
    console_logs_buffer = []
    last_event_type = None
    
    # Dictionary to track nodes by ID
    node_registry = {}
    
    # Function to recursively extract nodes from snapshots and mutations
    def register_nodes(node_data, parent_tag=None):
        try:
            if not isinstance(node_data, dict):
                return
                
            # Register this node if it has an ID
            if "id" in node_data:
                node_id = node_data.get("id")
                
                # Store basic node information
                node_info = {
                    "id": node_id,
                    "tagName": node_data.get("tagName", ""),
                    "attributes": {}
                }
                
                # Extract attributes if available
                if "attributes" in node_data:
                    node_info["attributes"] = node_data["attributes"]
                
                # Store textContent if available
                if "textContent" in node_data:
                    node_info["textContent"] = node_data["textContent"]
                    
                # Store parent tag for context
                if parent_tag:
                    node_info["parentTag"] = parent_tag
                    
                # Register the node
                node_registry[node_id] = node_info
                
            # Process child nodes recursively
            if "childNodes" in node_data:
                parent = node_data.get("tagName", "")
                for child in node_data["childNodes"]:
                    register_nodes(child, parent)
        except Exception as e:
            # Log error but continue processing
            print(f"Error registering node: {e}")
    
    # Function to get descriptive information about a node
    def get_node_description(node_id):
        if node_id not in node_registry:
            return "unknown element"
            
        node = node_registry[node_id]
        tag_name = node.get("tagName", "").lower()
        attributes = node.get("attributes", {})
        
        # Build descriptive element info
        parts = []
        
        # Add tag name first
        if tag_name:
            parts.append(tag_name)
        
        # Look for common identifying attributes
        if "name" in attributes:
            parts.append(f"name='{attributes['name']}'")
        if "id" in attributes:
            parts.append(f"id='{attributes['id']}'")
        if "placeholder" in attributes:
            parts.append(f"placeholder='{attributes['placeholder']}'")
        if "type" in attributes:
            parts.append(f"type='{attributes['type']}'")
        if "class" in attributes:
            parts.append(f"class='{attributes['class']}'")
        if "aria-label" in attributes:
            parts.append(f"aria-label='{attributes['aria-label']}'")
            
        # Add parent context if available
        if "parentTag" in node and tag_name not in ["input", "select", "textarea", "button"]:
            parts.append(f"in {node['parentTag']}")
            
        # Add text content as a hint if available
        if "textContent" in node and node["textContent"]:
            text = node["textContent"]
            if len(text) > 30:
                text = text[:27] + "..."
            parts.append(f"text='{text}'")
            
        return " ".join(parts)
    
    for event in events:
        # Calculate relative time
        relative_time = (event["timestamp"] - start_timestamp) / 1000.0
        minutes = int(relative_time // 60)
        seconds = int(relative_time % 60)
        timestamp = f"{minutes:02d}:{seconds:02d}"
        
        event_type = event_types[event.get("type", -1)]
        current_event_type = event_type
        
        # Process full snapshots to build node registry
        if event_type == "FullSnapshot":
            if "data" in event and "node" in event["data"]:
                register_nodes(event["data"]["node"])
                
        # Handle each event type
        if event_type == "IncrementalSnapshot":
            source = incremental_snapshot_event_source[event["data"].get("source", -1)]
            current_event_type = source  # Track specific source type
            
            # Process mutations to update node registry
            if source == "Mutation":
                try:
                    if "adds" in event["data"]:
                        for add in event["data"]["adds"]:
                            if "node" in add:
                                register_nodes(add["node"])
                    
                    # Handle attribute updates
                    if "attributes" in event["data"]:
                        for attr_update in event["data"]["attributes"]:
                            node_id = attr_update.get("id")
                            attr_name = attr_update.get("attributeName")
                            
                            if node_id in node_registry and attr_name:
                                if "attributes" not in node_registry[node_id]:
                                    node_registry[node_id]["attributes"] = {}
                                
                                # Try different possible attribute value keys
                                attr_value = None
                                for key in ["value", "attributes", "attribute"]:
                                    if key in attr_update:
                                        attr_value = attr_update[key]
                                        break
                                
                                # Only update if we found a value
                                if attr_value is not None:
                                    node_registry[node_id]["attributes"][attr_name] = attr_value
                except Exception as e:
                    # Log error but continue processing
                    print(f"Error processing mutation: {e}")
            
            # Handle mouse movements
            elif source == "MouseMove":
                positions = event["data"].get("positions", [])
                
                # Accumulate positions for later analysis
                if positions:
                    for pos in positions:
                        pos["event_timestamp"] = timestamp
                    mouse_positions_buffer.extend(positions)
                
                # Process buffer when reaching a certain size or type changes
                if len(mouse_positions_buffer) > 20 or (last_event_type != source and mouse_positions_buffer):
                    if len(mouse_positions_buffer) > 1:
                        summary = summarize_mouse_movements(mouse_positions_buffer)
                        if summary:
                            processed_events.append(summary)
                    mouse_positions_buffer = []
            
            # Handle mouse interactions (clicks, etc.)
            elif source == "MouseInteraction":
                interaction_type = event["data"].get("type")
                interaction_name = mouse_interaction_types.get(interaction_type, f"unknown({interaction_type})")
                
                # Only process clicks and double clicks
                if interaction_name not in ["click", "dblclick"]:
                    continue
                
                # Get target element information if available
                element_id = event["data"].get("id")
                
                # Try to determine what was clicked based on coordinates and other available information
                x, y = event["data"].get("x"), event["data"].get("y")
                interaction_description = ""
                
                # Look for special cases based on element data
                if element_id is not None:
                    # Look up node in registry
                    interaction_description = get_node_description(element_id)
                
                # Add description of the element area if coordinates are available
                if not interaction_description and x is not None and y is not None:
                    # Analyze position to infer what area was clicked
                    if y < 100:
                        interaction_description = "top navigation area"
                    elif x < 200:
                        interaction_description = "sidebar/navigation menu"
                    elif y > 600:
                        interaction_description = "bottom page area"
                    else:
                        interaction_description = "main content area"
                
                # Create a descriptive summary for the interaction
                if interaction_name == "click":
                    interaction_summary = f"Clicked on {interaction_description}" if interaction_description else "Clicked on page"
                elif interaction_name == "dblclick":
                    interaction_summary = f"Double clicked on {interaction_description}" if interaction_description else "Double clicked on page"
                else:
                    interaction_summary = f"{interaction_name} interaction with {interaction_description}" if interaction_description else f"{interaction_name} detected"
                
                processed_events.append({
                    "timestamp": timestamp,
                    "type": f"Mouse {interaction_name}",
                    "details": {
                        "x": x,
                        "y": y,
                        "target_description": interaction_description if interaction_description else "unknown element",
                        "element_id": element_id
                    }
                })
            
            # Handle scrolling
            elif source == "Scroll":
                scroll_data = {
                    "timestamp": timestamp,
                    "x": event["data"].get("x", 0),
                    "y": event["data"].get("y", 0)
                }
                
                scroll_events_buffer.append(scroll_data)
                
                # Process buffer when reaching a certain size or type changes
                if len(scroll_events_buffer) > 5 or (last_event_type != source and scroll_events_buffer):
                    if len(scroll_events_buffer) > 1:
                        summary = summarize_scroll_sequence(scroll_events_buffer)
                        if summary:
                            processed_events.append(summary)
                    scroll_events_buffer = []
            
            # Handle input changes
            elif source == "Input":
                try:
                    input_data = event["data"]
                    
                    # Determine input type and value
                    input_value = None
                    value_type = None
                    
                    if "text" in input_data:
                        input_value = input_data.get("text", "")
                        value_type = "text"
                    elif "isChecked" in input_data:
                        input_value = input_data.get("isChecked")
                        value_type = "checkbox"
                    
                    # Get node ID from the input event
                    node_id = input_data.get("id")
                    
                    # Look up node information from registry
                    element_info = "unknown element"
                    
                    # Try to get element info from node registry
                    if node_id is not None:
                        element_info = get_node_description(node_id)
                        
                        # If we still don't have good info, add a fallback with just the ID
                        if element_info == "unknown element":
                            # Try to infer input type from the value
                            inferred_type = ""
                            if value_type == "text":
                                # Check if it looks like a password field (all asterisks)
                                if input_value and all(c == '*' for c in input_value):
                                    inferred_type = "password field"
                                # Check if it looks like an email
                                elif '@' in input_value:
                                    inferred_type = "email field"
                                else:
                                    inferred_type = "text field"
                            elif value_type == "checkbox":
                                inferred_type = "checkbox"
                                
                            element_info = f"{inferred_type} (id={node_id})"
                    
                    # Create the input event
                    input_event = {
                        "timestamp": timestamp,
                        "type": "Input changed",
                        "details": {
                            "value_changed": input_value is not None,
                            "new_value": input_value,
                            "value_type": value_type,
                            "element": element_info
                        }
                    }
                    
                    # Add the event - we'll aggregate them in post-processing
                    processed_events.append(input_event)
                    
                except Exception as e:
                    # Log error but continue processing
                    print(f"Error processing input event: {e}")
                    # Add a minimal event with the available information
                    input_event = {
                        "timestamp": timestamp,
                        "type": "Input changed",
                        "details": {
                            "value_changed": True,
                            "element": f"input field (id={event['data'].get('id', 'unknown')})"
                        }
                    }
                    processed_events.append(input_event)
        
        # Handle console logs
        elif event_type == "Plugin" and event["data"]["plugin"] == "rrweb/console@1":
            # Set a specific type for console logs to properly track them
            current_event_type = "Console"
            
            console_data = {
                "timestamp": timestamp,
                "level": event["data"].get("level"),
                "message": event["data"].get("payload", {}).get("payload", [])
            }
            
            console_logs_buffer.append(console_data)
            
            # Process buffer when reaching a certain size or type changes
            if len(console_logs_buffer) > 5 or (last_event_type != "Console" and console_logs_buffer):
                if console_logs_buffer:
                    summary = summarize_console_logs(console_logs_buffer)
                    if summary:
                        processed_events.append(summary)
                console_logs_buffer = []
        
        # Handle page navigation (URLs)
        elif event_type in ["FullSnapshot", "Meta"]:
            href = event.get("data", {}).get("href")
            if href:
                processed_events.append({
                    "timestamp": timestamp,
                    "type": "Page navigation",
                    "details": {
                        "url": href
                    }
                })
        
        last_event_type = current_event_type
    
    # Process any remaining buffers
    if mouse_positions_buffer and len(mouse_positions_buffer) > 1:
        summary = summarize_mouse_movements(mouse_positions_buffer)
        if summary:
            processed_events.append(summary)
    
    if scroll_events_buffer and len(scroll_events_buffer) > 1:
        summary = summarize_scroll_sequence(scroll_events_buffer)
        if summary:
            processed_events.append(summary)
    
    if console_logs_buffer:
        summary = summarize_console_logs(console_logs_buffer)
        if summary:
            processed_events.append(summary)
    
    # Aggregate similar events (consecutive input changes to the same field, console logs with the same pattern)
    processed_events = aggregate_similar_events(processed_events)
    
    # Create a new list of derived insights about user behavior
    derived_insights = []
    
    # Track clicks
    clicks = [e for e in processed_events if e["type"].startswith("Mouse click")]
    
    # Track page views
    page_navigations = [e for e in processed_events if e["type"] == "Page navigation"]
    
    # Track input changes
    inputs = [e for e in processed_events if e["type"] == "Input changed"]
    
    # Get the latest timestamp
    latest_timestamp = processed_events[-1]["timestamp"] if processed_events else "00:00"
    latest_seconds = parse_timestamp(latest_timestamp)
    
    # Look for patterns like rapid clicking
    if len(clicks) >= 3:
        for i in range(len(clicks) - 2):
            start_time = parse_timestamp(clicks[i]["timestamp"])
            end_time = parse_timestamp(clicks[i+2]["timestamp"])
            
            if end_time - start_time < 3:  # 3 clicks in less than 3 seconds
                derived_insights.append({
                    "timestamp": clicks[i]["timestamp"],
                    "type": "User Behavior Insight",
                    "details": {
                        "pattern": "Rapid clicking",
                        "significance": "high",
                        "interpretation": "User may be experiencing frustration or UI responsiveness issues"
                    }
                })
                break  # Only add this insight once
    
    # Look for form filling (multiple input changes)
    if len(inputs) >= 3:
        # Use the timestamp of the last input for form filling insight
        form_timestamp = inputs[-1]["timestamp"] if inputs else latest_timestamp
        derived_insights.append({
            "timestamp": form_timestamp,
            "type": "User Behavior Insight", 
            "details": {
                "pattern": "Form filling",
                "field_count": len(inputs),
                "significance": "medium",
                "interpretation": "User is entering data in a form"
            }
        })
    
    # Add session overview
    summary_seconds = latest_seconds + 1
    summary_minutes = summary_seconds // 60
    summary_seconds_remainder = summary_seconds % 60
    summary_timestamp = f"{int(summary_minutes):02d}:{int(summary_seconds_remainder):02d}"
    
    derived_insights.append({
        "timestamp": summary_timestamp,
        "type": "Session Summary",
        "details": {
            "total_clicks": len(clicks),
            "total_pages": len(page_navigations),
            "total_inputs": len(inputs),
            "session_duration": get_session_duration(processed_events)
        }
    })
    
    # Sort insights by timestamp
    derived_insights.sort(key=lambda x: parse_timestamp(x["timestamp"]))
    
    # Make sure events are sorted chronologically by timestamp
    processed_events.sort(key=lambda x: parse_timestamp(x["timestamp"]))
    
    # Create final output with separate keys for events and insights
    output = {
        "metadata": {
            "generated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "total_events": len(processed_events),
            "session_duration": get_session_duration(processed_events),
            "event_categories": count_event_categories(processed_events),
            "total_console_logs": sum(event["details"].get("log_count", 0) for event in processed_events if event["type"] == "Console Logs")
        },
        "events": processed_events,
        "insights": derived_insights
    }
    
    # Write output file if specified
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2, cls=DecimalEncoder)
        print(f"LLM-friendly analysis has been saved to {output_file}")
    
    # Convert any Decimal objects to float before returning
    output_json = json.dumps(output, cls=DecimalEncoder)
    return json.loads(output_json)


# Use this as a simpler alternative to the full analyze_events
if __name__ == "__main__":
    # Static file paths instead of using argparse
    input_file = "recordings/rrweb/export3.1.json"
    output_file = "recordings/rrweb/export3.1.llm-summary.json"
    
    input_path = Path(input_file)
    output_path = Path(output_file)
    
    if not input_path.exists():
        print(f"Error: Input file {input_file} does not exist")
        exit(1)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_path.parent, exist_ok=True)
    
    # Generate summary but don't save it yet
    print(f"Analyzing {input_path}...")
    result = summarize_for_llm(str(input_path))
    
    # Modify the result to move derived insights outside of events
    events_with_insights = result["events"]
    
    # Separate regular events from insights
    regular_events = []
    insights = []
    
    for event in events_with_insights:
        if event["type"] in ["User Behavior Insight", "Session Summary"]:
            insights.append(event)
        else:
            regular_events.append(event)
    
    # Sort events chronologically by timestamp
    regular_events.sort(key=lambda x: parse_timestamp(x["timestamp"]))
    
    # Replace events with filtered list and add insights as separate key
    result["events"] = regular_events
    result["insights"] = insights
    
    # Count total console logs
    console_log_events = [event for event in regular_events if event["type"] == "Console Logs"]
    total_console_logs = sum(event["details"].get("log_count", 0) for event in console_log_events)
    
    # Add console log count to metadata
    result["metadata"]["total_console_logs"] = total_console_logs
    
    # Save the modified result
    with open(str(output_path), 'w') as f:
        json.dump(result, f, indent=2, cls=DecimalEncoder)
    
    print(f"Summary saved to {output_path}")
    print(f"Total console logs: {total_console_logs}")
