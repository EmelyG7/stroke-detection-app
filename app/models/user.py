from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    TECHNICIAN = "technician"

class User(BaseModel):
    id: Optional[str] = Field(default=None, description="Unique user ID")
    username: str = Field(..., min_length=3, max_length=50, description="Login username")
    full_name: str = Field(..., min_length=2, max_length=100, description="User full name")
    role: UserRole = Field(default=UserRole.TECHNICIAN, description="User role")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")