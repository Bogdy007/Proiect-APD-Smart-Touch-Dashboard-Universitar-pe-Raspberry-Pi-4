# QA — QA / Accessibility Engineer

**Student:** Neculcea S.A. Sabin · **GitHub:** (de completat)

Testele de integrare, auditul tactil și măsurătorile cerute la secțiunea 14 din cerință.

**Fișierele tale:** `tests/test_api_and_offline.py`, `docs/performance_and_qa_report.md`

## Sprint 1

- [ ] Trimite-i PM-ului username-ul de GitHub
- [ ] Rulează testele existente (`pytest`) și citește criteriile C1–C4 și secțiunea 14
- [ ] Plan de testare din `docs/widget_specifications.md`

## Sprint 2

- [ ] `tests/test_api_and_offline.py`: schema fiecărei rute; adaptoare forțate pe timeout, 500, 429 → se servește cache-ul cu vârsta datelor
- [ ] Audit tactil pe placa #2: ținte ≥ 44 × 44 px, contrast, lizibilitate de la distanță → lista către FE-1 / FE-2

## Sprint 3

- [ ] Latența adaptoarelor vs. cache, pe ≥ 50 de cereri
- [ ] Deconectarea rețelei: timpul de comutare pe cache și interactivitatea UI
- [ ] Rulare continuă ≥ 60 min: CPU, RAM, temperatură; timpul de boot până la dashboard
- [ ] Răspunsul vizual la atingere (< 150 ms)
- [ ] `docs/performance_and_qa_report.md` cu tabele și grafice

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/qa-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/qa-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
