
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(
    db: Session,
    email: str,
) -> Optional[User]:
    statement = select(User).where(User.email == email)

    return db.execute(statement).scalar_one_or_none()


def get_user_by_id(
    db: Session,
    user_id: str,
) -> Optional[User]:
    statement = select(User).where(User.id == user_id)

    return db.execute(statement).scalar_one_or_none()


def create_user(
    db: Session,
    organization_id,
    name: str,
    email: str,
    password_hash: str,
    role: str = "member",
) -> User:
    user = User(
        organization_id=organization_id,
        name=name,
        email=email,
        password_hash=password_hash,
        role=role,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user

