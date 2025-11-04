# Kobatella Backend (Prototype)

Prototype FastAPI backend implementing restricted transfers, alerting, and escrow flows for Kobatella.

## Requirements

- Python 3.13
- Virtual environment recommended

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and update values as needed.

```bash
cp .env.example .env
```

Environment variables:

- `APP_ENV`: Application environment label.
- `DATABASE_URL`: SQLAlchemy database URL (defaults to SQLite `kobatella.db`).
- `API_KEY`: Shared bearer token required for all endpoints.

## Running the API

Create the SQLite database (automatically handled on startup) and launch the server:

```bash
uvicorn app.main:app --reload
```

All requests must provide the header `Authorization: Bearer <API_KEY>`.

## Testing

Run the test suite with pytest:

```bash
pytest -q
```

## Seed Script

Populate sample users and authorization data:

```bash
python scripts/seed.py
```

This script creates two users, allowlists one recipient, and certifies another account for quick experimentation.
