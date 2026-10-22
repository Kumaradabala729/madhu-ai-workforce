
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AIEmployeeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(default="sales", min_length=1, max_length=50)
    description: Optional[str] = None
    language: str = Field(default="en", min_length=2, max_length=20)


class AIEmployeeUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    role: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = None
    language: Optional[str] = Field(default=None, min_length=2, max_length=20)
    status: Optional[str] = None


class AIEmployeeResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    role: str
    description: Optional[str]
    language: str
    status: str

    model_config = ConfigDict(from_attributes=True)
