from langchain_core.messages import SystemMessage, HumanMessage


import base64
import cv2

def map_timestamped_frames_to_messages(timestamped_frames):
    messages = []
    for timestamp, frame in timestamped_frames:
        _, buffer = cv2.imencode('.jpg', frame)
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        messages.append(HumanMessage(content=[
        {"type": "text", "text": f"Timestamp: {timestamp}"},
        {"type": "image_url",
                        "image_url": {"url": f'data:image/jpg;base64,{frame_base64}', "detail": "low"}}
        ]))
    return messages
