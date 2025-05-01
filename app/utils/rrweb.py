import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast


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

def merge_rrweb_batches(file_paths: List[str]) -> str:
    """
    Merge RRWeb batches into a single file.

    Args:
        file_paths: List of file paths to merge

    Returns:
        str: Path to the merged file
    """
    rrweb_json = {
        "sessionId": "",
        "startTime": "",
        "endTime": "",
        "data": []
    }

    for file_path in file_paths:
        with open(file_path, "r") as f:
            data = json.load(f)
            if rrweb_json["sessionId"] == "":
                rrweb_json["sessionId"] = data["sessionId"]
            if rrweb_json["startTime"] == "":
                rrweb_json["startTime"] = data["startTime"]
            if rrweb_json["endTime"] == "":
                rrweb_json["endTime"] = data["endTime"]
            rrweb_json["data"].extend(data["data"])
    
    output_path = file_paths[0].split("batch_")[0] + "events.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rrweb_json, f, indent=2)
    return output_path
