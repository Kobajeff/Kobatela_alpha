from app.db import init_engine, get_sessionmaker
from app.models.api_key import ApiKey, ApiScope
from app.utils.apikey import hash_key


def main() -> None:
    # 1) Initialise l'engine + SessionLocal à partir de ta config (app.config.get_settings)
    init_engine()
    SessionLocal = get_sessionmaker()
    db = SessionLocal()

    # 2) Choisis le token brut que tu utiliseras dans tes headers HTTP
    raw_token = "admin-dev-kobatela-001"

    try:
        # 3) Crée une clé API admin, comme dans make_api_key du conftest
        api_key = ApiKey(
            name="dev-admin-key",
            prefix="dev_admin",
            key_hash=hash_key(raw_token),
            scope=ApiScope.admin,
            is_active=True,
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)

        print("==========================================")
        print("✅ Admin API key created successfully")
        print("Use this key in your Authorization header:")
        print(f"    Authorization: Bearer {raw_token}")
        print(f"(DB id: {api_key.id}, scope: {api_key.scope})")
        print("==========================================")
    finally:
        db.close()


if __name__ == "__main__":
    main()
