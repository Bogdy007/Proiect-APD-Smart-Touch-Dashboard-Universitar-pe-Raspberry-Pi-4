# Registrul de riscuri — Echipa 5

> Responsabil: Project Manager · Actualizat la fiecare raport de sprint · Ultima actualizare: 5 noiembrie 2026

**Scala:** Probabilitate (P) și Impact (I) de la 1 (mic) la 3 (mare). Scor = P × I. Riscurile cu scor ≥ 6 se discută la fiecare ședință săptămânală.

| ID | Risc | P | I | Scor | Prevenire / reacție | Responsabil | Stare |
|---|---|---|---|---|---|---|---|
| R1 | Emailul universitar nu permite acces IMAP/OAuth2 pentru aplicații terțe | 3 | 2 | 6 | MAIL-1 verifică până pe 10 nov. Dacă e blocat, modul Mock-Email devine sursa principală (permis explicit de cerință), iar conectorul real se demonstrează pe un cont de test autorizat | MAIL-1, MAIL-2 | Deschis |
| R2 | Rolul SEC rămâne neacoperit | 2 | 3 | 6 | Căutăm colegul neînscris / anunțăm coordonatorul. Dacă rămâne liber după 13 nov., taskurile se împart: `credential_store.py` + XSS email → MAIL-1, `auth_manager.py` + `security_model.md` → TL, ecranul PIN → FE-2, XSS RSS → DATA-WN | PM | Deschis |
| R3 | Placa #2 nu e configurată la timp; acces la ea doar în laborator | 2 | 3 | 6 | DEVOPS configurează placa în M0; tot codul rulează și pe laptop (mock-uri, backend local), iar pe placă se testează în sesiuni de laborator planificate | DEVOPS | Deschis |
| R4 | Wi-Fi-ul din laborator are portal de autentificare care blochează placa | 2 | 3 | 6 | DEVOPS verifică în M0; alternative: cablu Ethernet sau hotspot de pe telefon pentru demo | DEVOPS | Deschis |
| R5 | Cardul microSD se corupe sau sistemul de pe placă se strică | 1 | 3 | 3 | Imagine de backup a cardului după configurare; `scripts/setup_kiosk.sh` reface totul dintr-o rulare | DEVOPS | Deschis |
| R6 | Modulele nu se integrează (formate diferite între adaptoare, cache și UI) | 2 | 3 | 6 | Contracte unice în `schemas.py` / `interfaces.py`; teste de contract; orice schimbare de schemă prin PR cu review TL | TL | Atenuat (contracte livrate pe 4 nov.) |
| R7 | Cache-ul și modul offline nu sunt gata pentru demo (criteriul C3) | 2 | 3 | 6 | CACHE începe din Sprint 1; QA testează deconectarea din Sprint 2; repetiția demo-ului include oprirea internetului | CACHE, QA | Deschis |
| R8 | API-urile externe limitează cererile (HTTP 429) sau cad în timpul demo-ului | 2 | 2 | 4 | Interval minim de 30 s per widget, backoff exponențial, respectarea `Retry-After`; cache-ul acoperă căderile | DATA-WN, CACHE | Deschis |
| R9 | Un membru nu contribuie sau întârzie constant | 2 | 2 | 4 | Issues asignate nominal și vizibile pe board; blocajele > 2 zile ajung la PM; taskurile critice se redistribuie la timp | PM | Deschis |
| R10 | Secrete (PIN, parole, chei API) urcate în Git | 1 | 3 | 3 | `.env` în `.gitignore`, `.env.example` fără valori; review pe PR; verificare de secrete în CI | SEC, DEVOPS | Deschis |
| R11 | UI-ul e lent pe RPi (> 150 ms) sau backend-ul are scurgeri de memorie | 2 | 2 | 4 | UI-ul citește doar din cache-ul local; apeluri asincrone; rulare de 60 min monitorizată în Sprint 3 | FE-1, FE-2, QA | Deschis |
| R12 | Vacanța de iarnă reduce ritmul înainte de Sprint 3 | 3 | 1 | 3 | MVP-ul complet până pe 18 dec.; perioada tampon doar pentru documentație și teste | PM | Deschis |
| R13 | Demo-ul eșuează live (rețea, placă, timp depășit) | 2 | 3 | 6 | Repetiție generală pe placă înainte de prezentare; video de backup de 2–3 minute; scenariu de ~12 min cronometrat | PM | Deschis |

## Istoric

| Data | Modificare |
|---|---|
| 5 nov. 2026 | Versiunea inițială; R6 atenuat după livrarea contractelor de date de către TL |
