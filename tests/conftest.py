"""Test configuration."""
import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# --- Config env par défaut
os.environ.setdefault("DATABASE_URL", "sqlite:///./kobatella_test.db")
os.environ.setdefault("API_KEY", "test-secret-key")
os.environ.setdefault("PSP_WEBHOOK_SECRET", "test-psp-secret")

from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.db import get_db  # noqa: E402

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
def anyio_backend() -> str:
    return "asyncio"
