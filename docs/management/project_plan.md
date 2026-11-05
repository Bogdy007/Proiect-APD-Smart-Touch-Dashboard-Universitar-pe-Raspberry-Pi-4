# Plan de proiect — Smart Touch Dashboard (Echipa 5)

> Responsabil: Project Manager (Panainte Bogdan-Dumitru) · Versiune 1.0 · 5 noiembrie 2026
> Disciplina: Achiziția și Prelucrarea Datelor (APD), 2026–2027 · Coordonator: Ș.l. dr. ing. Dragoș Bratu

## 1. Obiectiv

Un dashboard tactil pe Raspberry Pi 4 #2 care adună într-un singur ecran emailul universitar, vremea și știrile RSS, funcționează și fără internet din cache-ul local, protejează datele private cu PIN și pornește singur în mod kiosk.

**Termenul obligatoriu** este prezentarea finală anunțată pe e-Learning (orientativ ~20 ianuarie 2027). Termenele sprinturilor de mai jos sunt cele recomandate în cerință și le folosim ca termene interne.

## 2. Ce livrăm (MVP obligatoriu)

1. Interfață tactilă pe RPi 4 #2, cu pornire automată la boot (kiosk).
2. Widget Email: expeditor, subiect, previzualizare — prin autentificare oficială sau prin modul Mock-Email.
3. Widget Vreme conectat la un API extern (Open-Meteo).
4. Widget Știri din surse RSS configurabile.
5. Configurarea widget-urilor din UI (activare, ordine, interval de refresh).
6. Cache local cu funcționare offline și afișarea vechimii datelor.
7. Autentificare PIN pentru datele sensibile și panou de monitorizare a performanței.

Funcționalități opționale, doar după ce MVP-ul e stabil: mod zi/noapte, evidențierea emailurilor urgente.

## 3. Echipa

| Cod | Rol | Student | Livrabile principale |
|---|---|---|---|
| PM | Project Manager | Panainte Ș. Bogdan-Dumitru | `docs/management/`, `docs/widget_specifications.md`, `scripts/report_generator.py` |
| TL | Technical Lead | Moroșanu S. Răzvan-Andrei | `docs/architecture.md`, `src/backend/`, ≥ 15 code review-uri |
| FE-1 | Dashboard, Vreme, Știri | Bulearcă C. Mihnea-Ștefan | `DashboardGrid.*`, `WeatherWidget.*`, `NewsWidget.*` |
| FE-2 | Email, Setări, Performanță | Cimpoeșu C. Ioan | `EmailWidget.*`, `SettingsModal.*`, `PerformanceWidget.*` |
| MAIL-1 | Conector email real | Gaiu I. Ioana-Mădălina | `src/adapters/mail_client.py`, `mail_parser.py` |
| MAIL-2 | Mock-Email și filtre | Ciocan S. Mihai-Cătălin | `src/adapters/mock_mail_provider.py`, `mail_service.py` |
| DATA-WN | Meteo + RSS | Ciobănoiu G.M. Rareș-Alexandru | `src/adapters/weather_adapter.py`, `news_rss_adapter.py` |
| SEC | Autentificare și securitate | **loc liber** (vezi R2 în registrul de riscuri) | `src/security/`, `docs/security_model.md` |
| CACHE | Cache + scheduler | Pricop G.L. Andrei-Bogdan | `src/cache/cache_manager.py`, `scheduler.py` |
| QA | Teste + accesibilitate | Neculcea S.A. Sabin | `tests/test_api_and_offline.py`, `docs/performance_and_qa_report.md` |
| DEVOPS | RPi, kiosk, CI | Calu M. Radu-Alexandru | `scripts/setup_kiosk.sh`, `*.service`, `src/monitoring/rpi_metrics.py`, `.github/workflows/ci.yml` |

Taskurile detaliate ale fiecărui rol: [`docs/management/taskuri/`](taskuri/README.md).

## 4. Calendar și obiectivele fiecărei etape

| Etapă | Perioadă | Gata la final înseamnă |
|---|---|---|
| Milestone 0 | 26 oct. – 6 nov. 2026 | Repo + roluri asumate, arhitectură și contracte de date (**gata pe 4 nov.**), placa #2 configurată |
| Sprint 1 | 7 – 24 nov. 2026 | Vremea, știrile și emailul (cel puțin Mock) vin prin API și apar pe touchscreen |
| Sprint 2 | 25 nov. – 18 dec. 2026 | MVP complet: cache cu mod offline, setări widget-uri, PIN, pornire automată în kiosk |
| Tampon (vacanță) | 19 dec. 2026 – 4 ian. 2027 | Fără ședințe obligatorii; documentație și teste |
| Sprint 3 | 5 – 19 ian. 2027 | Măsurătorile din secțiunea 14, testul de deconectare, repetiția demo-ului, video de backup |
| Prezentare finală | ~20 ian. 2027 (e-Learning) | Demo live ~12 min, 3–4 prezentatori, întrebări individuale pentru toți 11 |

Fiecare etapă are un milestone pe GitHub; progresul se urmărește pe board-ul din GitHub Projects.

## 5. Dependențe critice

1. **Contractele TL** (`schemas.py`, `interfaces.py`) — livrate pe 4 nov. Orice modificare se face prin PR separat, cu incrementarea `SCHEMA_VERSION`.
2. **Placa #2 configurată (DEVOPS, 6 nov.)** — necesară pentru rezoluția UI-ului, testele pe hardware și kiosk.
3. **Accesul la emailul universitar (MAIL-1, 10 nov.)** — decide dacă demo-ul folosește sursa reală sau Mock-Email.
4. **Mock-Email (MAIL-2)** — FE-2 construiește widget-ul de email pe aceste date.
5. **Cache-ul (CACHE)** — toate rutele reale servesc din el; condiționează criteriul C3.

Până la livrarea modulelor reale, `src/backend/app.py` rulează pe `mock_services.py`, astfel încât frontend-ul și modulele se dezvoltă în paralel.

## 6. Proces de lucru

- **Taskuri:** fiecare task = un GitHub Issue asignat nominal, cu label-ul rolului și milestone-ul sprintului. Tot ce blochează alți colegi are label-ul `blocker`.
- **Branch-uri:** `feat/<rol>-<descriere>` sau `fix/<rol>-<descriere>`, create din `main` actualizat.
- **Pull Requests:** `main` e protejat — intrarea se face doar prin PR, cu minimum o aprobare (TL pentru `src/backend/` și pentru scheme) și testele verzi în CI. Descrierea PR-ului conține `Closes #<issue>`.
- **Contribuție individuală:** fiecare urcă doar de pe contul propriu; nu se urcă cod scris de altcineva.
- **Secrete:** niciodată în Git — doar în `.env` (ignorat) sau în stocarea criptată a modulului SEC.

### Definition of Done

Un task e gata când: codul e pe `main` prin PR aprobat, testele trec, modulul respectă interfața din `interfaces.py`, iar issue-ul e închis.

## 7. Comunicare și ritm

- **Canal:** serverul de Discord al echipei (anunțuri, întrebări, resurse).
- **Ședință săptămânală:** 15 minute — ce am terminat, ce urmează, ce mă blochează. Ziua se stabilește la kick-off.
- **Raport de sprint:** la finalul fiecărui sprint, în `docs/management/sprint_<n>_report.md` — ce s-a livrat, ce a alunecat, riscuri noi.
- **Escaladare:** un blocaj mai vechi de 2 zile ajunge la PM; o problemă de arhitectură la TL; o problemă de acces sau organizare la coordonator.

## 8. Criterii de acceptare la demo

Proiectul e acceptat doar dacă toate patru sunt îndeplinite:

| Criteriu | Ce demonstrăm | Responsabili |
|---|---|---|
| C1 | Pornire automată pe RPi 4 #2; totul se face doar din touchscreen | DEVOPS, FE-1, FE-2 |
| C2 | Email (expeditor, subiect, preview), vreme și știri funcționale și actualizate | MAIL-1, MAIL-2, DATA-WN |
| C3 | Se oprește internetul: fără erori, date din cache, stare offline și vârsta datelor vizibile | CACHE, FE-1 |
| C4 | Credențiale protejate; raport cu latențe, cache hit-rate și resurse RPi | SEC, QA, PM |

## 9. Notare și cum ne asigurăm că o acoperim

| Componentă | Pondere | Ce facem pentru ea |
|---|---|---|
| Produsul și demo-ul | 40% | MVP complet până pe 18 dec., Sprint 3 doar pentru măsurători și repetiții |
| Contribuția individuală | 35% | Fiecare are fișierele lui, commit-uri și PR-uri de pe contul propriu |
| Procesul de inginerie | 15% | Issues asignate, milestone-uri, PR-uri cu review, CI, instalare reproductibilă din README |
| Întrebările individuale | 10% | Fiecare repetă o explicație de 1–2 minute despre modulul lui înainte de demo |

## 10. Documente de management

- Registrul de riscuri: [`risk_register.md`](risk_register.md)
- Taskurile pe roluri: [`taskuri/`](taskuri/README.md)
- Rapoartele de sprint: `sprint_1_report.md`, `sprint_2_report.md`, `sprint_3_report.md` (la finalul fiecărui sprint)
