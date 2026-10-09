
from typing import Literal

from pydantic import BaseModel


class MemberRoleUpdateRequest(BaseModel):
    role: Literal["admin", "member"]