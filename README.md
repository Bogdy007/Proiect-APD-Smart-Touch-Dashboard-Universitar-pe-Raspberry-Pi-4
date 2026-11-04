# Smart Touch Dashboard — Echipa 5 (APD 2026–2027)

Dashboard tactil pe Raspberry Pi 4 #2: email universitar, vreme, știri RSS, cache offline, PIN lock și mod kiosk.

## Stack

- **Backend:** Python 3.11+ · FastAPI · SQLite (cache) · httpx
- **Frontend:** React + Vite, rulat în Chromium `--kiosk` pe Raspberry Pi 4 #2
- **Deploy:** Raspberry Pi OS · servicii systemd · GitHub Actions (CI)

## Pornire rapidă (dezvoltare)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn src.backend.app:app --reload
```

Documentația API: http://127.0.0.1:8000/docs · Teste: `pytest`

## Documentație

- [Arhitectură și specificație API](docs/architecture.md)

## Structură

| Folder | Owner |
|---|---|
| `src/backend/` | TL |
| `src/frontend/` | FE-1, FE-2 |
| `src/adapters/` | MAIL-1, MAIL-2, DATA-WN |
| `src/cache/` | CACHE |
| `src/security/` | SEC |
| `src/monitoring/`, `scripts/`, `.github/` | DEVOPS |
| `tests/` | QA (+ fiecare pentru modulul propriu) |
| `docs/` | toți (management: PM) |
