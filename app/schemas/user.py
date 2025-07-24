from pydantic import BaseModel
from typing import Optional

class UserCreate(BaseModel):
    username: str
    password_hash: str  # Will be hashed in the route
    full_name: str
    role: str