# SEC — Authentication & Security Engineer

**Student:** LOC LIBER — de alocat · **GitHub:** —

PIN tactil cu auto-lock, credențiale sigure, protecție XSS. Dacă locul rămâne liber după 13 nov., taskurile se împart: `credential_store.py` și XSS email → MAIL-1, `auth_manager.py` și `security_model.md` → TL, ecranul PIN → FE-2, XSS RSS → DATA-WN.

**Fișierele tale:** `src/security/auth_manager.py`, `src/security/credential_store.py`, `docs/security_model.md`

**Ce implementezi:** `AuthService`: `unlock(pin) -> SessionInfo`, `lock(token)`, `validate(token) -> bool`, `status(token) -> AuthStatus`; `AuthError` cu `INVALID_PIN` / `LOCKED_OUT`.

## Sprint 2 — intră în MVP

- [ ] `auth_manager.py`: PIN doar ca hash (bcrypt/argon2), sesiune cu expirare, auto-lock la inactivitate, blocare după 5 PIN-uri greșite
- [ ] `credential_store.py`: secrete doar din `.env` (în `.gitignore`) sau stocare criptată
- [ ] Nicio dată externă afișată ca HTML brut (fără `innerHTML` / `dangerouslySetInnerHTML`)
- [ ] `docs/security_model.md` + teste de securitate; cu DEVOPS, verificare de secrete în CI
- [ ] Înlocuiește `MockAuthService` din `default_services()`

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/sec-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/sec-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
