"""Administration commands.

Usage: uv run python -m app.cli create-admin --email admin@example.com
"""

import argparse
import getpass

from sqlmodel import Session, select

from app.auth import create_local_user, hash_password, validate_password
from app.database import DATABASE_URL, create_db_engine, init_db
from app.models import User


def create_admin(email: str, password: str, display_name: str = "") -> User:
    engine = create_db_engine(DATABASE_URL)
    init_db(engine)
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == email.strip().lower())).first()
        if existing is None:
            return create_local_user(
                session,
                email=email,
                password=password,
                display_name=display_name,
                role="admin",
                status="active",
            )
        validate_password(password)
        existing.password_hash = hash_password(password)
        existing.role, existing.status = "admin", "active"
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="Create or promote a local administrator")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="")
    args = parser.parse_args()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    user = create_admin(args.email, password, args.name)
    print(f"Administrator ready: {user.email}")


if __name__ == "__main__":
    main()
