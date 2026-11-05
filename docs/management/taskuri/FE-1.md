# FE-1 — Frontend — Dashboard, Vreme, Știri

**Student:** Bulearcă C. Mihnea-Ștefan · **GitHub:** Croederul

Layout-ul tactil al dashboard-ului, widget-urile Vreme și Știri, bara de stare.

**Fișierele tale:** `src/frontend/components/DashboardGrid.*`, `WeatherWidget.*`, `NewsWidget.*`

## M0

- [ ] Proiectul React + Vite în `src/frontend`, împreună cu FE-2
- [ ] Rezoluția touchscreen-ului de la DEVOPS → layout-ul pe ea

## Sprint 1

- [ ] `DashboardGrid.*`: grid responsiv, `touch-action`, ținte ≥ 44 × 44 px, contrast ridicat
- [ ] Bara de stare: ceas, dată, online/offline din `GET /api/health`
- [ ] `WeatherWidget.*` din `GET /api/weather`: temperatură, resimțită, umiditate, vânt, pictogramă, prognoză orară și zilnică
- [ ] `NewsWidget.*` din `GET /api/news`: titlu, sursă, oră; atingerea deschide rezumatul
- [ ] Pe fiecare widget: „actualizat acum X min” din `meta.age_seconds`

## Sprint 2

- [ ] Indicator „Mod Offline — date din urmă cu X minute” când `meta.is_stale` e `true`
- [ ] Tastatură virtuală pe ecran (URL RSS, PIN), folosită și de FE-2
- [ ] Grid-ul respectă configurația din `GET /api/config` (widget-uri active, ordine)
- [ ] WebSocket `/ws`: re-cere widget-ul la `data_updated`; orice atingere răspunde vizual sub 150 ms

## Sprint 3

- [ ] Repară problemele din auditul QA; opțional mod zi/noapte

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/fe1-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/fe1-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
