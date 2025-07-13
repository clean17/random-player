from dataclasses import dataclass

@dataclass
class ChatPreviewDTO:
    id: int = None
    chat_id: int = None
    origin_url: str = None
    thumbnail_url: str = None
    title: str = None
    description: str = None
    created_at: str = None
