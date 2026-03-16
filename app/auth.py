"""Password hashing and optional default admin seed."""
import bcrypt

from app.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


async def ensure_admin_seed() -> None:
    """Create default admin user (admin / Tam123!) if no users exist."""
    async with AsyncSessionLocal() as session:
        r = await session.execute(select(User).limit(1))
        if r.scalars().first() is not None:
            return
        admin = User(
            username="admin",
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            password_hash=hash_password("Tam123!"),
            role="admin",
            active=True,
        )
        session.add(admin)
        await session.commit()
