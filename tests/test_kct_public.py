import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.api_key import ApiKey, ApiScope
from app.models.user import User
from app.utils.apikey import find_valid_key
from app.utils.apikey import hash_key
from app.schemas.escrow import EscrowCreate
from app.services import escrow as escrow_service


def _make_user_with_key(db_session, *, public_tag: str) -> tuple[User, str]:
    user = User(
        username=f"user-{uuid.uuid4().hex[:8]}",
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        public_tag=public_tag,
    )
    db_session.add(user)
    db_session.flush()

    token = f"token-{uuid.uuid4().hex}"
    api_key = ApiKey(
        name="test",
        prefix="test",
        key_hash=hash_key(token),
        scope=ApiScope.sender,
        user_id=user.id,
    )
    db_session.add(api_key)
    db_session.commit()
    fetched = find_valid_key(db_session, token)
    assert getattr(fetched, "user_id", None) == user.id
    return user, token


async def _create_public_project(client, db_session) -> tuple[int, str, User]:
    user, token = _make_user_with_key(db_session, public_tag="GOV")
    response = await client.post(
        "/kct_public/projects",
        json={
            "label": "Public Project",
            "project_type": "health",
            "country": "CI",
            "domain": "public",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201, response.json()
    payload = response.json()
    assert payload["domain"] == "public"
    assert Decimal(str(payload["total_amount"])) == Decimal("0")
    assert payload["current_milestone"] is None
    return payload["id"], token, user


@pytest.mark.anyio("asyncio")
async def test_private_user_access_forbidden(client, db_session):
    _, token = _make_user_with_key(db_session, public_tag="private")

    response = await client.post(
        "/kct_public/projects",
        json={
            "label": "Public Project",
            "project_type": "health",
            "country": "CI",
            "domain": "public",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    error = response.json().get("error", {})
    assert error.get("code") == "PUBLIC_ACCESS_FORBIDDEN"


@pytest.mark.anyio("asyncio")
async def test_create_public_project(client, db_session):
    await _create_public_project(client, db_session)


@pytest.mark.anyio("asyncio")
async def test_attach_public_escrow_and_aggregation(client, db_session):
    project_id, token, user = await _create_public_project(client, db_session)

    client_user = User(
        username=f"client-{uuid.uuid4().hex[:8]}",
        email=f"client-{uuid.uuid4().hex[:8]}@example.com",
    )
    provider_user = User(
        username=f"provider-{uuid.uuid4().hex[:8]}",
        email=f"provider-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add_all([client_user, provider_user])
    db_session.flush()

    escrow = escrow_service.create_escrow(
        db_session,
        EscrowCreate(
            client_id=client_user.id,
            provider_id=provider_user.id,
            amount_total=Decimal("250.00"),
            currency="USD",
            release_conditions={"proof": "delivery"},
            deadline_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
            domain="public",
        ),
        actor="test",
        current_user=user,
    )
    escrow_id = escrow.id

    attach_resp = await client.post(
        f"/kct_public/projects/{project_id}/mandates",
        json={"escrow_id": escrow_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert attach_resp.status_code in {200, 201}

    project_resp = await client.get(
        f"/kct_public/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert project_resp.status_code == 200
    project = project_resp.json()
    assert Decimal(str(project["total_amount"])) == Decimal("250")
    assert Decimal(str(project["released_amount"])) == Decimal("0")


@pytest.mark.anyio("asyncio")
async def test_list_public_projects(client, db_session):
    project_id, token, _ = await _create_public_project(client, db_session)

    list_resp = await client.get(
        "/kct_public/projects",
        params={"domain": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    projects = list_resp.json()
    assert any(p["id"] == project_id for p in projects)
