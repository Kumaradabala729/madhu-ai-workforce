from pydantic import BaseModel, Field


class OrganizationUpdateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=100)