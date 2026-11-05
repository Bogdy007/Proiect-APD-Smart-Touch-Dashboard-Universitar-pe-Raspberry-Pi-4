# TL — Technical Lead

**Student:** Moroșanu S. Răzvan-Andrei · **GitHub:** mororazvan04

Arhitectura, contractele de date, API-ul backend și code review pe PR-urile echipei.

**Fișierele tale:** `docs/architecture.md`, `src/backend/app.py`, `src/backend/schemas.py`, `src/backend/interfaces.py`

## Gata

- [x] Stack ales (FastAPI + React/Vite) și scheletul repo-ului
- [x] `schemas.py` + `interfaces.py` (contractele dintre module) — SCHEMA_VERSION 1.0.0
- [x] `app.py` cu toate rutele, pe mock-uri; 13 teste de contract
- [x] `docs/architecture.md` v1 cu specificația API

## Sprint 1–2

- [ ] Code review pe fiecare PR al echipei — ținta e minimum 15 review-uri până la final (livrabil individual)
- [ ] Integrarea modulelor reale în `default_services()` pe măsură ce sunt livrate
- [ ] Rutele private (preview email, setări) protejate de modulul de autentificare real
- [ ] Verifică că niciun apel de rețea nu blochează (totul `async`)

## Sprint 3

- [ ] `docs/architecture.md` final: achiziție → normalizare → cache → API → UI
- [ ] Împreună cu QA: verificarea scurgerilor de memorie la rularea de 60 min

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/tl-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/tl-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
