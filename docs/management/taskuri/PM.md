# PM — Project Manager

**Student:** Panainte Ș. Bogdan-Dumitru · **GitHub:** Bogdy007

Planificarea sprinturilor, backlog-ul pe GitHub, registrul de riscuri, raportul de latență/disponibilitate și coordonarea demo-ului.

**Fișierele tale:** `docs/management/`, `docs/widget_specifications.md`, `scripts/report_generator.py`

## M0 — săptămâna asta

- [ ] Protecție pe `main`: merge doar prin PR, minimum 1 aprobare
- [ ] Milestones: Sprint 1 (24 nov.), Sprint 2 (18 dec.), Sprint 3 (19 ian.), Demo final (~20 ian.)
- [ ] Labels pe rol (`pm`, `tl`, `fe-1`, … `devops`) + `blocker`; board GitHub Project (Backlog → Done)
- [ ] Issues asignate nominal pentru toate taskurile Sprint 1
- [ ] Username-urile GitHub lipsă: MAIL-1, CACHE, QA
- [ ] Rezolvă locul SEC (coleg neînscris sau redistribuire după 13 nov.)
- [ ] Kick-off de 15–20 min cu toată echipa
- [ ] `docs/management/project_plan.md` și `docs/management/risk_register.md`

## Sprint 1

- [ ] `docs/widget_specifications.md`: per widget — câmpuri, refresh implicit, stare offline, stare de eroare, interacțiuni tactile + scenariile de test pentru QA
- [ ] `docs/management/sprint_1_report.md`

## Sprint 2

- [ ] Sesiune în laborator cu toată aplicația pe placa #2
- [ ] `scripts/report_generator.py`: citește telemetria de la CACHE → medie, p95, min/max, % disponibilitate (markdown/CSV)
- [ ] Raport Sprint 2 + actualizarea registrului de riscuri

## Sprint 3

- [ ] `report_generator.py` pe datele testului de 60 min → rezultatele către QA
- [ ] Scenariul demo (~12 min), cei 3–4 prezentatori, repetiție generală pe placă
- [ ] Video de backup (2–3 min); README complet; raport Sprint 3

## Cum lucrezi

1. `git checkout main && git pull`
2. `git checkout -b feat/pm-<descriere>`
3. Lucrezi doar în fișierele tale, cu commit-uri mici, pe contul tău.
4. `git push -u origin feat/pm-<descriere>` → deschizi Pull Request cu `Closes #<issue>` în descriere.
5. Ceri review (TL sau colegul cu care ai dependență); merge doar după aprobare și teste verzi.

Contractele (ce primești și ce returnezi) sunt în [`src/backend/interfaces.py`](../../../src/backend/interfaces.py) și [`src/backend/schemas.py`](../../../src/backend/schemas.py); fluxul și rutele API în [`docs/architecture.md`](../../architecture.md). Până livrezi modulul real, `app.py` rulează pe implementările din `src/backend/mock_services.py` — modulul tău înlocuiește mock-ul din `default_services()` printr-un PR.

← [Înapoi la toate rolurile](README.md)
