from dataclasses import dataclass

@dataclass
class PostDTO:
    id: int = None
    user_id: int = None
    type: str = None
    title: str = None
    content: str = None
    created_at: str = None  # datetime 사용 가능
    updated_at: str = None
    realname: str = None
    view_count: int = None