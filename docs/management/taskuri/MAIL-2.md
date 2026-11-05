# MAIL-2 — Mail Integration — Mock-Email, filtre

**Student:** Ciocan S. Mihai-Cătălin · **GitHub:** ciocanul444

Motorul Mock-Email (cerut în cerința proiectului), filtrele și comutarea real/mock. FE-2 lucrează pe datele tale.

**Fișierele tale:** `src/adapters/mock_mail_provider.py`, `src/adapters/mail_service.py`

**Ce implementezi:** `MailProvider` cu `mode = "mock"` → `fetch_inbox(limit) -> list[EmailDetail]`; erorile simulate ridică `SourceError`.

## Sprint 1 — prioritar

- [ ] `mock_mail_provider.py`: ~30 mesaje academice realiste (secretariat, profesori, e-Learning, burse), mesaje noi la interval aleator, erori simulate (timeout, autentificare, 500) cu probabilitate configurabilă
- [ ] `mail_service.py`: alege între real și mock după `MAIL_MODE` (Strategy/Adapter)
- [ ] Filtre: necitite, prioritare, căutare, trunchiere sigură a preview-ului
- [ ] Teste unitare; înlocuiește mock-ul de email din `default_services()`

## Sprint 2

- [ ] Integrare cu cache-ul; marcare ca citit

## Sprint 3

- [ ] Scenarii de erori pentru testele de reziliență ale QA

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/mail2-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/mail2-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
