from dataclasses import dataclass

@dataclass
class TempChatDTO:
    id: int = None
    temp_message: str = None
    user_id: int = None
    updated_at: str = None  # datetime 사용 가능
    username: str = None
    chat_room_id: int = None
