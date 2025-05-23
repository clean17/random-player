from dataclasses import dataclass

@dataclass
class UserDTO:
    id: int = None
    username: str = None
    email: str = None
    password: str = None
    role: str = None
    created_at: str = None  # datetime 사용 가능
    updated_at: str = None  # datetime 사용 가능
    login_attempt: int = None
    is_active: bool = True
    is_lockout: bool = False
    lockout_time: str = None
