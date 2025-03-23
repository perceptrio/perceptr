import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast


class RRWebSessionUtils:
    def __init__(self, file_path: str):
        self.file_path = file_path
        with open(file_path, "r", encoding="utf-8") as f:
            self.session = json.load(f)
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

        self.userIdentity = self.session["userIdentity"]

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


if __name__ == "__main__":
    try:
        # Example file path - replace with your actual file path
        file_path = "recordings/rrweb/t.json"

        # Initialize session utils
        session = RRWebSessionUtils(file_path)

        # Print session summary
        print(session.get_session_summary())
        print(f"Start time: {session.get_start_time()}")
        print(f"End time: {session.get_end_time()}")
        print(f"Duration: {session.get_duration()}")
        print(f"Events: {len(session.get_events())}")
        print(f"User identity: {session.get_user_identity()}")

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
