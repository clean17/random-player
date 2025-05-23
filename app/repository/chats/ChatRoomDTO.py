from dataclasses import dataclass

@dataclass
class ChatRoomDTO:
    id: int = None
    number_of_participants: int = None
    created_at: str = None  # datetime 사용 가능
    updated_at: str = None  # datetime 사용 가능
    room_name: str = None
