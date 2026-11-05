# DATA-WN — Weather / News Data Developer

**Student:** Ciobănoiu G.M. Rareș-Alexandru · **GitHub:** DR-SHAZAM05

Adaptorul meteo și agregatorul de știri RSS.

**Fișierele tale:** `src/adapters/weather_adapter.py`, `src/adapters/news_rss_adapter.py`

**Ce implementezi:** `WeatherProvider.fetch(latitude, longitude, location_name) -> WeatherData` și `NewsProvider.fetch(sources) -> list[NewsItem]`; `httpx.AsyncClient` cu timeout; la eșec `SourceError` (cu `retry_after_s` la 429).

## Sprint 1

- [ ] `weather_adapter.py` pe Open-Meteo (fără cheie API): vremea curentă + prognoză orară și zilnică, maparea codurilor la `WeatherCondition`
- [ ] `news_rss_adapter.py` cu `feedparser`: mai multe fluxuri, HTML curățat, deduplicare (id = sha1 al link-ului), ordonare descrescătoare
- [ ] 3–4 fluxuri reale (tehnologie, știință, anunțuri universitare) verificate
- [ ] Teste pe răspunsuri stricate: JSON invalid, XML rupt, câmpuri lipsă, flux gol
- [ ] Înlocuiește mock-urile de vreme și știri din `default_services()`

## Sprint 2

- [ ] Validarea unui flux RSS nou înainte de salvare
- [ ] Tratarea 429 și `Retry-After`, împreună cu CACHE

## Sprint 3

- [ ] Demo: adăugarea unui flux nou; latențe meteo și RSS

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/datawn-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/datawn-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
