from dataclasses import dataclass

@dataclass
class ChatDTO:
    id: int = None
    message: str = None
    user_id: int = None
    created_at: str = None  # datetime 사용 가능
    username: str = None
    chat_room_id: int = None
