from pydantic import BaseModel, EmailStr
from pydantic import Field


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    organization_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)