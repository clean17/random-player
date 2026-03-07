from dataclasses import dataclass

@dataclass
class VideoCallDTO:
    id: int = None
    user_id: int = None
    created_at: str = None  # datetime 사용 가능
    updated_at: str = None  # datetime 사용 가능

