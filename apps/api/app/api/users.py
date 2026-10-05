
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User


router = APIRouter(
    prefix="/api/users",
    tags=["Users"],
)


@router.get("/me")
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    return {
        "message": "Authenticated user profile",
        "user": {
            "id": str(current_user.id),
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role,
            "organization_id": str(current_user.organization_id),
        },
    }

