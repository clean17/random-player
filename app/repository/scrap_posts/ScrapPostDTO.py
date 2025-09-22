from dataclasses import dataclass

@dataclass
class ScrapPostDTO:
    id: int = None
    created_at: str = None  # datetime 사용 가능
    account: str = None
    post_urls: str = None
    type: str = None
