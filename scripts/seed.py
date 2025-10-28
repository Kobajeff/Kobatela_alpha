"""Seed sample data for the Kobatella prototype."""
from __future__ import annotations

from datetime import UTC, datetime

from dotenv import load_dotenv

load_dotenv()

from app import models
from app.config import get_settings
from app.db import SessionLocal, engine


def main() -> None:
    settings = get_settings()
    print(f"Using database: {settings.database_url}")

    models.Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    try:
        alice = models.User(username="alice", email="alice@example.com")
        bob = models.User(username="bob", email="bob@example.com")
        session.add_all([alice, bob])
        session.commit()
        session.refresh(alice)
        session.refresh(bob)

        allow = models.AllowedRecipient(owner_id=alice.id, recipient_id=bob.id)
        certify = models.CertifiedAccount(user_id=bob.id, level=models.CertificationLevel.GOLD, certified_at=datetime.now(tz=UTC))
        session.add_all([allow, certify])
        session.commit()
        print("Seed data inserted.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
