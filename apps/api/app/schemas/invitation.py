
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    role: Literal["member", "admin"] = "member"


class InvitationCreateResponse(BaseModel):
    id: str
    email: EmailStr
    role: str
    expires_at: str
    invite_url: str
