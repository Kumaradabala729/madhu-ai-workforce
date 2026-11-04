from typing import Optional

from pydantic import BaseModel, Field


class AIEmployeeExecutionCreateRequest(BaseModel):
    task: str = Field(min_length=1)
    input_data: Optional[dict] = None
