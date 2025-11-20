"""Test configuration."""
import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
import hashlib

# --- Config env par défaut
os.environ.setdefault("DATABASE_URL", "sqlite:///./kobatella_test.db")
os.environ.setdefault("API_KEY", "test-secret-key")
os.environ.setdefault("PSP_WEBHOOK_SECRET", "test-psp-secret")
os.environ.setdefault("KOB_ENV", "dev")

from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.db import get_db  # noqa: E402
from app.models import (
    Merchant,
    SpendCategory,
    UsageMandate,
    UsageMandateStatus,
    User,
)
from app.models.api_key import ApiKey, ApiScope
from app.utils.apikey import hash_key

DB_PATH = Path("./kobatella_test.db")

def _run_migrations() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")

# --- (1) Reset DB fichier au début de la session
if DB_PATH.exists():
    DB_PATH.unlink()

engine = create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
    future=True,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                                   future=True, expire_on_commit=False)

# --- (2) Construire le schéma via Alembic uniquement
_run_migrations()

@pytest.fixture(scope="session", autouse=True)
def startup_app() -> Iterator[None]:
    asyncio.run(app.router.startup())
    yield
    asyncio.run(app.router.shutdown())

@pytest.fixture
def db_session() -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

@pytest.fixture(autouse=True)
def override_db_dependency(db_session: Session) -> Iterator[None]:
    def _get_db() -> Iterator[Session]:
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client

@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['API_KEY']}"}


@pytest.fixture
def make_api_key(db_session: Session) -> Callable[..., ApiKey]:
    def _factory(
        name: str,
        key: str,
        scope: ApiScope = ApiScope.sender,   # 👈 valeur par défaut ajoutée ici
        is_active: bool = True,
    ) -> ApiKey:
        # exemple de corps – garde ton implémentation actuelle si elle diffère
        api_key = ApiKey(
            name=name,
            prefix="test_" + scope.value,
            key_hash=hash_key(key),
            scope=scope,
            is_active=is_active,
        )
        db_session.add(api_key)
        db_session.commit()
        db_session.refresh(api_key)
        return api_key

    return _factory



@pytest.fixture
def sender_headers(make_api_key: Callable[..., ApiKey]) -> dict[str, str]:
    token = f"sender-{uuid4().hex}"
    make_api_key(name=f"sender-{uuid4().hex}", key=token, scope=ApiScope.sender)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(make_api_key: Callable[..., ApiKey]) -> dict[str, str]:
    token = f"admin-{uuid4().hex}"
    make_api_key(name=f"admin-{uuid4().hex}", key=token, scope=ApiScope.admin)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def make_users_merchants_mandate(db_session: Session) -> Callable[..., tuple[User, User, int]]:
    """Factory creating sender, beneficiary, merchant and active mandate."""

    def _factory(
        *,
        sender: str = "diaspora",
        beneficiary: str = "beneficiary",
        total: str = "100.00",
        currency: str = "USD",
        expires_delta: timedelta = timedelta(days=7),
        merchant_certified: bool = True,
    ) -> tuple[User, User, int]:
        timestamp = datetime.now(tz=UTC)

        sender_user = User(
            username=f"{sender}-{uuid4().hex[:8]}",
            email=f"{sender}-{uuid4().hex[:8]}@example.com",
        )
        beneficiary_user = User(
            username=f"{beneficiary}-{uuid4().hex[:8]}",
            email=f"{beneficiary}-{uuid4().hex[:8]}@example.com",
        )

        category = SpendCategory(
            code=f"CAT-{uuid4().hex[:6]}",
            label=f"Category {beneficiary}",
        )
        merchant = Merchant(
            name=f"merchant-{uuid4().hex[:8]}",
            category=category,
            is_certified=merchant_certified,
        )

        db_session.add_all([sender_user, beneficiary_user, category, merchant])
        db_session.flush()

        mandate = UsageMandate(
            sender_id=sender_user.id,
            beneficiary_id=beneficiary_user.id,
            total_amount=Decimal(total),
            currency=currency,
            allowed_category_id=None,
            allowed_merchant_id=merchant.id,
            expires_at=timestamp + expires_delta,
            status=UsageMandateStatus.ACTIVE,
        )
        db_session.add(mandate)
        db_session.flush()

        return sender_user, beneficiary_user, merchant.id

    return _factory
