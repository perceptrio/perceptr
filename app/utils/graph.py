import base64
from typing import List, Tuple

import cv2
import numpy as np
from langchain_core.messages import HumanMessage, SystemMessage


def map_timestamped_frames_to_messages(
    timestamped_frames: List[Tuple[str, np.ndarray, str]]
) -> List[HumanMessage]:
    messages = []
    for timestamp, frame, summary in timestamped_frames:
        _, buffer = cv2.imencode(".jpg", frame)
        frame_base64 = base64.b64encode(buffer).decode("utf-8")
        messages.append(
            HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": f"Timestamp: {timestamp}, RRWeb Summary: {summary}",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{frame_base64}",
                            "detail": "low",
                        },
                    },
                ]
            )
        )
    return messages
