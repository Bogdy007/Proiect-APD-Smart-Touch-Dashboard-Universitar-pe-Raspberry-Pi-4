# DEVOPS — DevOps / Raspberry Pi Engineer

**Student:** Calu M. Radu-Alexandru · **GitHub:** RaduC05

Placa #2, pornirea automată în kiosk, metricile hardware și CI-ul.

**Fișierele tale:** `scripts/setup_kiosk.sh`, `*.service`, `src/monitoring/rpi_metrics.py`, `.github/workflows/ci.yml`

**Ce implementezi:** `MetricsProvider.read() -> SystemMetrics` (temperatură CPU, încărcare, RAM, online).

## M0 — urgent, până pe 6 nov.

- [ ] Raspberry Pi OS pe microSD, SSH, rețea, calibrarea touchscreen-ului
- [ ] Spune echipei rezoluția ecranului și dacă Wi-Fi-ul din laborator are portal de login
- [ ] Imagine de backup a cardului
- [ ] `.github/workflows/ci.yml`: `pytest` (+ build frontend când există) la fiecare PR

## Sprint 1

- [ ] Script de deploy pe placă: clonare, venv, `pip install`, build frontend
- [ ] `src/monitoring/rpi_metrics.py` cu `psutil` + temperatura CPU; înlocuiește mock-ul de metrici

## Sprint 2 — criteriul C1

- [ ] Serviciu systemd pentru backend, cu repornire automată
- [ ] Chromium `--kiosk --noerrdialogs --disable-infobars` la boot, fără tastatură/mouse; ecranul nu se stinge
- [ ] `scripts/setup_kiosk.sh` care configurează totul dintr-o rulare + fișierele `.service`

## Sprint 3

- [ ] Timpul de boot până la dashboard, cu QA
- [ ] Secțiunea de deployment din `README.md`

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/devops-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/devops-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
