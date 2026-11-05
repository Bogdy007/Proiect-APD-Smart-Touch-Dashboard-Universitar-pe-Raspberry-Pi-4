# MAIL-1 — Mail Integration — conector real

**Student:** Gaiu I. Ioana-Mădălina · **GitHub:** (de completat)

Conectorul la emailul universitar prin metode oficiale și parsarea mesajelor.

**Fișierele tale:** `src/adapters/mail_client.py`, `src/adapters/mail_parser.py`

**Ce implementezi:** `MailProvider` cu `mode = "real"` → `fetch_inbox(limit) -> list[EmailDetail]`; la orice eșec ridici `SourceError`.

## Până pe 10 nov. — cel mai important pas

- [ ] Trimite-i PM-ului username-ul de GitHub
- [ ] Verifică dacă emailul `student.unitbv.ro` permite IMAP sau OAuth2 pentru aplicații terțe. Dacă e blocat, modul Mock devine sursa principală, iar conectorul real se testează pe un cont de test autorizat (IMAP peste SSL)

## Sprint 1

- [ ] `mail_client.py`: conexiune IMAP/SSL sau OAuth2, ultimele N mesaje (antete + începutul corpului), starea „citit”
- [ ] `mail_parser.py`: decodarea `From`, `Subject`, `Date` (inclusiv diacritice codate), text din multipart/HTML, sanitizare, preview ≤ 500 caractere
- [ ] Teste unitare pe `.eml`-uri: UTF-8 cu diacritice, quoted-printable, base64, multipart

## Sprint 2

- [ ] Credențialele doar din `.env` / stocarea SEC
- [ ] Integrare cu cache-ul

## Sprint 3

- [ ] Latența conectorului real; demonstrarea ambelor moduri (real și mock)

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/mail1-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/mail1-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
