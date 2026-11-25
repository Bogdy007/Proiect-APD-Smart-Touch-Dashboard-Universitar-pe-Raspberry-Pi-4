# Raport Sprint 1 — Echipa 5

> Responsabil: Project Manager (Panainte Bogdan-Dumitru) · Perioada: 7 – 24 noiembrie 2026 · Redactat: 25 noiembrie 2026
> Sursa datelor: istoricul Git al repo-ului, Pull Request-urile și rularea testelor pe `main` la 25 nov.

## 1. Pe scurt

Obiectivul Sprint 1 era ca vremea, știrile și emailul (cel puțin Mock) să vină prin API și să apară pe touchscreen. **Obiectivul a fost atins parțial.** Adaptoarele de vreme și știri sunt gata și integrate pe `main`, frontend-ul are proiectul inițializat, iar cache-ul a fost implementat în ultima zi, dar nu e încă integrat. Partea de email, placa Raspberry Pi și CI-ul nu au fost începute.

Din 11 membri, **5 au contribuit cu cod sau documente** în acest sprint. Ceilalți 6 nu au niciun commit.

## 2. Ce s-a livrat pe `main`

| PR | Ce conține | Autor | Review | Issue închis |
|---|---|---|---|---|
| #28 | Specificația widget-urilor și 24 de scenarii de test | PM (Bogdan) | aprobat de TL | #4 |
| #29 | Serviciile sincrone nu mai blochează bucla de evenimente | TL (Răzvan) | aprobat de PM | — |
| #30 | Documentarea verificării apelurilor blocante | TL (Răzvan) | aprobat de PM | — |
| #31 | Proiectul React + Vite în `src/frontend` | FE-1 (Mihnea) | aprobat de TL | — |
| #32 | Adaptorul meteo pe Open-Meteo | DATA-WN (Rareș) | modificări cerute, apoi aprobat de TL | #22 |
| #33 | Adaptorul de știri RSS/Atom | DATA-WN (Rareș) | modificări cerute, apoi aprobat de TL | #23 |

În Milestone 0, înainte de sprint, intraseră deja contractele de date și API-ul (#1, TL) și planul de proiect, registrul de riscuri și taskurile pe roluri (#27, PM).

**Teste pe `main`: 123, toate trec.**

La #32 și #33, review-ul TL a găsit două probleme de securitate (citirea unui fișier local prin `feedparser` și cod executabil rămas în rezumatele RSS) și una de robustețe (valori invalide de la API care nu ajungeau la `SourceError`). Toate au fost corectate și acoperite cu teste înainte de merge.

## 3. În lucru, încă neintegrat

| Rol | Ce există | Ce lipsește |
|---|---|---|
| FE-1 (Mihnea) | Branch `feature/dashboard-grid`: layout 800×480 cu bara de stare; build-ul trece | Pull Request |
| CACHE (Andrei) | Branch-uri `feat/cache-sqlite-manager` și `feat/cache-scheduler`: SQLite, `ConfigStore`, `CacheService`, scheduler cu backoff; respectă interfețele, testele trec | Pull Request-uri; mai multe teste pentru scheduler; legarea în `default_services()` |

## 4. Ce nu a fost început

| Rol | Membru | Taskuri Sprint 1 rămase | Impact |
|---|---|---|---|
| DEVOPS | Radu | placa #2 (#8), CI (#9), deploy (#10), `rpi_metrics.py` (#11) | Nu s-a testat nimic pe hardware; PR-urile intră fără verificare automată |
| MAIL-1 | Ioana | verificarea accesului IMAP/OAuth2 (#18), conectorul real (#19) | Nu știm încă dacă demo-ul poate folosi emailul real |
| MAIL-2 | Mihai | Mock-Email (#20), `mail_service.py` (#21) | Blochează widget-ul de email (FE-2) |
| FE-2 | Ioan | `EmailWidget` (#16) | Depinde de MAIL-2; invitația pe GitHub nu era acceptată la ultima verificare |
| QA | Sabin | planul de testare (#26) | Fără plan de testare înaintea integrării |
| SEC | Adrian | — (taskurile SEC sunt în Sprint 2) | Rolul e acoperit; poate începe |

## 5. Contribuții în sprint (7 – 24 nov.)

Commit-uri proprii (fără merge-uri), pe `main` și pe branch-uri:

| Membru | Commit-uri | PR-uri integrate | Review-uri făcute |
|---|---|---|---|
| Rareș (DATA-WN) | 6 | 2 | — |
| Andrei (CACHE) | 4 | 0 (în lucru) | — |
| Mihnea (FE-1) | 3 | 1 | — |
| Răzvan (TL) | 2 | 2 | 4 PR-uri (#28, #31, #32, #33), la #32 și #33 cu modificări cerute |
| Bogdan (PM) | 1 | 1 | 2 (#29, #30) |
| Radu, Ioana, Mihai, Ioan, Sabin, Adrian | 0 | 0 | 0 |

Pe lângă commit-uri, PM a configurat repo-ul (protecția pe `main`, label-uri, milestone-uri, 24 de issues asignate, board-ul GitHub Projects) și a coordonat echipa pe Discord.

## 6. Ce a mers bine

- **Contractele de date ale TL au funcționat:** adaptoarele lui Rareș și cache-ul lui Andrei s-au scris separat și se potrivesc fără modificări.
- **Review-ul a prins probleme reale de securitate** înainte să ajungă pe `main` (#33).
- **Procesul pe GitHub e respectat:** tot codul a intrat prin Pull Request cu aprobare, nimic direct pe `main`.

## 7. Ce nu a mers

- **Jumătate din echipă nu a început.** Taskurile au fost asignate de la începutul sprintului, dar majoritatea contribuțiilor au apărut abia în ultimele 3 zile.
- **Lipsește CI-ul:** PR-urile apar cu „No checks”, iar testele au fost rulate doar manual.
- **Placa #2 nu e configurată**, deși termenul era în Milestone 0. Rezoluția 800×480 folosită de FE-1 nu e încă confirmată pe hardware.
- **Commit-uri neasociate conturilor GitHub:** emailul din Git nu era legat de contul GitHub la unii membri, așa că acele contribuții nu apăreau pe profil. PM și-a corectat contul; restul echipei trebuie să verifice.

## 8. Riscuri actualizate

| ID | Risc | Stare după Sprint 1 |
|---|---|---|
| R1 | Emailul universitar fără acces IMAP/OAuth2 | **Deschis** — verificarea nu a fost făcută |
| R2 | Rolul SEC neacoperit | **Închis** — rolul a fost preluat de Adrian |
| R3 | Placa #2 neconfigurată | **Materializat** — se escaladează la DEVOPS |
| R6 | Module care nu se integrează | **Atenuat** — adaptoarele și cache-ul respectă contractele |
| R7 | Cache-ul nu e gata pentru C3 | **Atenuat** — implementat, rămâne integrarea |
| R9 | Membri care nu contribuie | **Materializat** — 6 din 11 fără commit-uri |
| R14 (nou) | PR-uri integrate fără teste automate | **Deschis** — se rezolvă prin CI (DEVOPS) |

## 9. Ce urmează în Sprint 2 (25 nov. – 18 dec.)

Obiectiv: **MVP complet** — cache cu mod offline, setări pentru widget-uri, PIN, pornire automată în kiosk.

Prioritățile, în ordine:

1. **CACHE:** PR-urile pentru cache și scheduler, apoi legarea în `default_services()`.
2. **DEVOPS:** placa #2 și CI-ul, cât mai repede; apoi kiosk-ul și serviciul systemd (C1).
3. **MAIL-2 → FE-2:** Mock-Email, apoi `EmailWidget` pe datele lui.
4. **FE-1:** PR pentru grid, apoi `WeatherWidget` și `NewsWidget` pe adaptoarele deja integrate.
5. **DATA-WN:** legarea adaptoarelor în `default_services()` și validarea surselor RSS noi.
6. **SEC:** `auth_manager.py` și `credential_store.py`.
7. **QA:** planul de testare și primele teste de integrare pentru modul offline.
8. **MAIL-1:** răspunsul despre emailul universitar, ca să decidem modul demo-ului.

**Măsuri de proces:**
- Taskurile neterminate din Sprint 1 se mută în milestone-ul Sprint 2.
- PM verifică board-ul de două ori pe săptămână; un membru fără activitate o săptămână e contactat direct, iar dacă situația continuă, se anunță coordonatorul.
- Fiecare membru verifică dacă emailul din `git config user.email` e adăugat în contul său de GitHub.
