# CACHE — Data Processing / Cache Engineer

**Student:** Pricop G.L. Andrei-Bogdan · **GitHub:** (de completat)

Cache-ul SQLite, scheduler-ul și modul offline — miezul criteriului C3. E cel mai mare modul: începe imediat.

**Fișierele tale:** `src/cache/cache_manager.py`, `src/cache/scheduler.py`

**Ce implementezi:** `CacheService` (get_emails, get_email, mark_read, get_weather, get_news, refresh, get_telemetry) și `ConfigStore` (config + surse RSS). Nu ridici excepții pentru surse căzute: întorci date vechi cu `meta.is_stale = True`.

## Sprint 1

- [ ] Trimite-i PM-ului username-ul de GitHub
- [ ] SQLite: tabel de cache (sursă, cheie, JSON, fetched_at), `widget_config`, `news_sources`, `telemetry`
- [ ] `cache_manager.py`: citire/scriere, TTL pe sursă, `Envelope` cu `meta` completat corect
- [ ] `scheduler.py`: refresh în fundal la `refresh_interval_s` al fiecărui widget

## Sprint 2

- [ ] Stale-while-revalidate + fallback offline cu `age_seconds`; reluarea automată a sincronizării
- [ ] Backoff `min(base · 2^n, 15 min)` cu jitter; respectarea `retry_after_s`
- [ ] Telemetria hit/miss și latență pentru `PerformanceWidget` și `report_generator.py`
- [ ] Teste: expirare TTL, fallback offline; înlocuiește mock-ul de cache din `default_services()`

## Sprint 3

- [ ] Datele pentru comparația latență sursă vs. cache (≥ 50 cereri pe sursă)

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/cache-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/cache-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
