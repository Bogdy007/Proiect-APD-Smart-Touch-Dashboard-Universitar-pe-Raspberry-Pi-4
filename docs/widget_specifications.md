# Specificația widget-urilor și scenariile de test

> Responsabil: Project Manager (Panainte Bogdan-Dumitru) · Versiune 1.0 · 10 noiembrie 2026
> Bazată pe contractul v1.0.0 din [`src/backend/schemas.py`](../src/backend/schemas.py) și pe [`docs/architecture.md`](architecture.md).
> Orice modificare se face prin PR. Schimbările care ating API-ul sau schemele cer și review de la TL.

Documentul spune **ce afișează** fiecare widget, **de unde ia datele**, **cum se comportă** în fiecare stare și **cum îl testăm**. FE-1 și FE-2 construiesc după el, iar QA scrie testele pe scenariile din secțiunea 9.

## 1. Reguli comune pentru toate widget-urile

### 1.1 Ecran și atingere

| Regulă | Valoare |
|---|---|
| Țintă minimă de atingere | 44 × 44 px pentru orice buton, rând de listă sau iconiță |
| Spațiu între ținte | minimum 8 px |
| Text de bază | minimum 16 px; titluri de widget minimum 20 px |
| Contrast | minimum 4.5 : 1 pentru text, în ambele teme |
| Răspuns vizual la atingere | sub 150 ms (stare apăsată / ripple), chiar dacă cererea durează mai mult |
| Interacțiuni | doar atingere simplă și derulare verticală; fără hover, dublu-clic sau click dreapta |
| Tastatură | doar tastatura virtuală pe ecran (FE-1), afișată doar pentru câmpuri text |
| Navigare externă | **interzisă** — în kiosk nu se deschide niciun link spre internet |

### 1.2 Stările unui widget

Fiecare widget de date (Email, Vreme, Știri) tratează toate stările de mai jos. Starea se deduce din `meta` (`Envelope`).

| Stare | Când | Ce vede utilizatorul |
|---|---|---|
| Încărcare | prima cerere, încă fără răspuns | schelet (placeholder gri), fără spinner pe tot ecranul |
| Live | `meta.source = live` sau `mock`, `is_stale = false` | datele + eticheta de vechime discretă |
| Din cache (offline) | `meta.is_stale = true` | datele vechi + insignă **„Offline · acum X min”** pe widget |
| Gol | `items = []` și `is_stale = false` | mesaj neutru (ex. „Niciun email nou”) |
| Fără date | `items = []` și `is_stale = true` (prima pornire fără internet) | „Date indisponibile — se reîncearcă automat” |
| Eroare de rețea locală | backend-ul nu răspunde deloc | păstrează ultimele date afișate + bara de stare trece pe offline |

Un widget **nu afișează niciodată** o eroare tehnică brută (stack trace, `500`, JSON). Textul `meta.error` nu se arată utilizatorului; îl vede doar panoul Sistem.

### 1.3 Eticheta de vechime

Calculată din `meta.age_seconds`:

| Vechime | Text |
|---|---|
| sub 60 s | „acum” |
| 1–59 min | „acum X min” |
| 1–23 h | „acum X h” |
| 24 h sau mai mult | data, ex. „3 nov.” |

### 1.4 Actualizare automată

- Widget-ul **nu face polling**. Re-cere datele când primește pe `/ws` evenimentul `data_updated` cu numele lui.
- Intervalele de refresh le aplică scheduler-ul (CACHE), după `refresh_interval_s` din configurare.
- La reconectarea WebSocket-ului (backoff 1 s → 30 s), fiecare widget își re-cere datele o dată.

### 1.5 Securitate în UI

- Textul din email și RSS se afișează **doar ca text**, niciodată ca HTML (`innerHTML` / `dangerouslySetInnerHTML` sunt interzise pe date externe).
- La evenimentul `auth_locked`, orice previzualizare de email și panoul de setări se închid imediat.

## 2. Structura ecranului — `DashboardGrid` + bara de stare (FE-1)

**Date:** `GET /api/config` (ce widget-uri apar și în ce ordine), `GET /api/health`, evenimentele `/ws`.

**Bara de stare (sus, fixă):**

| Element | Sursă | Detalii |
|---|---|---|
| Ceas | ceasul local | `HH:MM`, format 24 h |
| Dată | ceasul local | ex. „marți, 10 noiembrie” |
| Indicator conexiune | `health.online` și `connectivity_changed` | verde „Online” / portocaliu „Offline” |
| Mod email | `health.mail_mode` | eticheta „Mock” vizibilă doar când e `mock` |
| Lacăt | `GET /api/auth/status` | deschis / închis; atingerea blochează (`POST /api/auth/lock`) sau deschide ecranul PIN |
| Setări | — | deschide `SettingsModal` (cere PIN) |

**Grid:**
- Afișează doar widget-urile cu `enabled = true`, în ordinea `position` (0 primul).
- La `config_updated` re-cere `/api/config` și rearanjează fără reîncărcarea paginii.
- Layout-ul se proiectează pe rezoluția touchscreen-ului plăcii #2 (vezi întrebarea Î1, secțiunea 10).

**Acceptare:** pornește direct în dashboard, fără bară de browser; se poate folosi complet fără tastatură și mouse.

## 3. Widget Email (FE-2)

**Date:** `GET /api/email?filter=all|unread|priority&limit=20` → `Envelope[EmailList]`; previzualizare `GET /api/email/{id}` 🔒 → `Envelope[EmailDetail]`.
**Refresh implicit:** 120 s.

**Lista (vizibilă fără PIN):**

| Câmp | Afișare |
|---|---|
| `sender_name` | numele expeditorului, bold dacă `is_read = false` |
| `subject` | un rând, trunchiat cu „…” |
| `received_at` | `HH:MM` dacă e azi, altfel „3 nov.” |
| `is_priority` | marcaj vizibil (ex. bandă colorată sau „!”) |
| `unread_count` | insignă numerică în antetul widget-ului |

**Interacțiuni:**
1. **Filtre:** trei butoane-filă — „Toate”, „Necitite”, „Prioritare”. Schimbarea filtrului re-cere lista.
2. **Atingerea unui email:**
   - cu sesiune deblocată → se deschide previzualizarea;
   - fără sesiune (răspuns `AUTH_REQUIRED`) → apare ecranul PIN, iar după deblocare se deschide direct emailul ales.
3. **Previzualizarea** arată: `sender_name` + `sender_address`, `subject`, data completă, `preview` (text simplu, maximum 500 caractere). Se închide cu un buton „Închide” de minimum 44 px. După deschidere, emailul apare ca citit.
4. **Refresh manual:** buton în antet → `POST /api/refresh/email` (202). Iconița se rotește până la `data_updated` sau maximum 10 s.

**Acceptare (C2):** expeditorul, subiectul și previzualizarea se văd și funcționează atât în modul `real`, cât și în modul `mock`.

## 4. Widget Vreme (FE-1)

**Date:** `GET /api/weather` → `Envelope[WeatherData]`. Locația vine din configurare (implicit Brașov).
**Refresh implicit:** 600 s.

| Zonă | Câmpuri | Afișare |
|---|---|---|
| Antet | `location_name` | numele orașului |
| Acum | `current.temperature_c`, `condition`, `description` | temperatura rotunjită la grad (`8°`), pictograma condiției, descrierea |
| Detalii | `feels_like_c`, `humidity_pct`, `wind_kmh` | „Resimțită 5°”, „Umiditate 76%”, „Vânt 12 km/h” |
| Pe ore | `hourly` | următoarele 12 ore, derulabile orizontal: oră, pictogramă, temperatură |
| Pe zile | `daily` | următoarele 5 zile: ziua, pictogramă, `min / max`, `precipitation_pct` dacă există |

**Pictograme:** câte una pentru fiecare valoare din `WeatherCondition` (`clear`, `partly_cloudy`, `cloudy`, `fog`, `drizzle`, `rain`, `snow`, `thunderstorm`, `unknown`). `unknown` folosește o pictogramă neutră, nu un spațiu gol.

**Interacțiuni:** derulare orizontală pe prognoza orară; refresh manual (`POST /api/refresh/weather`).

**Acceptare (C2):** datele vin din API-ul extern real și se actualizează singure la intervalul configurat.

## 5. Widget Știri (FE-1)

**Date:** `GET /api/news?source_id=&limit=30` → `Envelope[NewsList]`; lista surselor din `GET /api/news/sources`.
**Refresh implicit:** 900 s.

**Lista:**

| Câmp | Afișare |
|---|---|
| `title` | maximum 2 rânduri, trunchiat cu „…” |
| `source_name` | sub titlu, text secundar |
| `published_at` | vechime relativă („acum 25 min”) |

Știrile sunt deja ordonate descrescător de backend; UI-ul nu le reordonează.

**Interacțiuni:**
1. **Filtru pe sursă:** butoane-pastilă „Toate” + câte una pentru fiecare sursă activă → re-cere cu `source_id`.
2. **Atingerea unei știri** deschide un panou cu `title`, `source_name`, data completă și `summary` (text simplu, maximum 600 caractere). Link-ul **nu se deschide** (kiosk); se afișează doar domeniul sursei ca text.
3. **Refresh manual:** `POST /api/refresh/news`.

**Acceptare (C2):** știrile vin din fluxurile RSS configurate; o sursă adăugată din Setări apare în listă după următorul refresh.

## 6. Widget Sistem — `PerformanceWidget` (FE-2)

**Date:** evenimentul `metrics` pe `/ws` (la 5 s), cu `GET /api/system/metrics` la deschidere; `GET /api/system/telemetry` pentru surse.
**Refresh implicit:** 30 s pentru telemetria surselor; metricile vin în timp real.

| Indicator | Câmp | Afișare |
|---|---|---|
| Temperatură CPU | `cpu_temp_c` | `52 °C`; „n/a” dacă e `null` (ex. pe laptop) |
| Încărcare CPU | `cpu_load_pct` | procent + bară |
| Memorie | `ram_used_mb`, `ram_total_mb` | „1 240 / 3 790 MB” + bară |
| Rețea | `online` | Online / Offline |
| Per sursă | `avg_latency_ms`, hit rate, `consecutive_failures`, `last_success_at` | tabel cu Email, Vreme, Știri |

Hit rate = `cache_hits / (cache_hits + cache_misses)`, afișat în procente.

**Praguri de culoare pentru temperatură:** sub 60 °C normal, 60–75 °C avertisment, peste 75 °C critic. Placa începe să-și reducă frecvența în jur de 80 °C.

**Acceptare (C4):** valorile se schimbă în timp real pe placa #2 și corespund cu `vcgencmd measure_temp` / `htop`.

## 7. Panoul de setări — `SettingsModal` (FE-2)

**Acces:** doar cu sesiune deblocată (toate modificările sunt 🔒). Fără sesiune, butonul de setări deschide ecranul PIN.
**Date:** `GET` / `PUT /api/config`; sursele RSS prin `/api/news/sources`.

**Secțiunea Widget-uri:**

| Setare | Control | Valori |
|---|---|---|
| Activ | comutator | da / nu |
| Ordine | butoane ▲ / ▼ (fără drag) | schimbă `position` |
| Interval de refresh | listă de opțiuni | 30 s, 1 min, 2 min, 5 min, 10 min, 15 min, 30 min, 1 h (în limita 30–3600 s) |

**Secțiunea Surse RSS:**
- Lista surselor cu comutator activ / inactiv → `PATCH /api/news/sources/{id}`.
- **Adaugă:** nume (1–80 caractere) + URL, introduse cu tastatura virtuală → `POST /api/news/sources`. Un URL invalid primește mesaj lângă câmp, fără să închidă panoul.
- **Șterge:** confirmare în aplicație („Ștergi sursa X?”), fără dialog de browser → `DELETE /api/news/sources/{id}`.

**Secțiunea Generale:** blocare automată după `auto_lock_minutes` (1–60, implicit 5) și tema (`auto`, `light`, `dark`).

**Salvare:** butonul „Salvează” trimite `PUT /api/config`. La `INVALID_CONFIG` se afișează motivul și setările rămân nesalvate. După salvare, dashboard-ul se rearanjează la evenimentul `config_updated`.

**Acceptare:** preferințele rămân după repornirea plăcii (persistate de CACHE în SQLite).

## 8. Ecranul PIN (FE-2, cu modulul SEC)

**Date:** `POST /api/auth/unlock`, `POST /api/auth/lock`, `GET /api/auth/status`.

- Tastatură numerică pe ecran: cifrele 0–9, „Șterge”, „OK”; butoane de minimum 64 × 64 px.
- PIN de 4–8 cifre, afișat ca puncte, niciodată ca cifre.
- **PIN greșit** (`INVALID_PIN`, 401): câmpul se golește și apare „PIN greșit”, cu numărul de încercări rămase din `failed_attempts` (din maximum 5).
- **Blocare temporară** (`LOCKED_OUT`, 429): tastatura se dezactivează și apare o numărătoare inversă până la `locked_out_until`.
- **Succes:** tokenul primit se ține doar în memorie (nu în `localStorage`) și se trimite ca `Authorization: Bearer <token>`.
- **Blocare automată:** după `auto_lock_minutes` fără atingeri, sau manual din lacătul din bara de stare.

**Acceptare (C4):** fără PIN nu se poate citi nicio previzualizare și nu se poate modifica nicio setare.

## 9. Scenarii de test (pentru QA)

Fiecare scenariu are un ID folosit în issue-uri, PR-uri și în `docs/performance_and_qa_report.md`. „Auto” = test în `pytest`; „Manual” = verificat pe placa #2.

| ID | Scenariu | Pași | Rezultat așteptat | Criteriu | Tip |
|---|---|---|---|---|---|
| T-01 | Pornire automată | Alimentează placa #2 | Dashboard-ul complet apare fără nicio intervenție; se măsoară timpul | C1 | Manual |
| T-02 | Doar touchscreen | Parcurge T-03…T-12 fără tastatură și mouse | Toate acțiunile se pot face prin atingere | C1 | Manual |
| T-03 | Listă email | Deschide dashboard-ul | Expeditor, subiect și oră pentru ultimele emailuri; insigna de necitite corectă | C2 | Auto + Manual |
| T-04 | Filtre email | Atinge „Necitite”, apoi „Prioritare” | Lista se filtrează corect | C2 | Auto |
| T-05 | Previzualizare cu PIN | Atinge un email fără sesiune, introdu PIN-ul | Apare ecranul PIN, apoi previzualizarea; emailul devine citit | C2, C4 | Auto + Manual |
| T-06 | Comutare real / mock | Pornește cu `MAIL_MODE=mock`, apoi `real` | Ambele moduri afișează emailuri; eticheta „Mock” apare doar în modul mock | C2 | Auto |
| T-07 | Vreme | Deschide dashboard-ul | Date curente + prognoză orară și zilnică pentru Brașov | C2 | Auto + Manual |
| T-08 | Știri | Deschide dashboard-ul | Știri din mai multe surse, cele mai noi primele, fără duplicate | C2 | Auto |
| T-09 | Adăugare sursă RSS | Setări → Adaugă sursă validă | Sursa apare în listă, iar știrile ei după refresh | C2 | Manual |
| T-10 | URL RSS invalid | Setări → Adaugă un URL greșit | Mesaj de eroare lângă câmp; sursa nu se salvează | — | Auto |
| T-11 | Configurare widget-uri | Dezactivează Știri, mută Vreme pe ultima poziție, salvează, repornește placa | Layout-ul se schimbă imediat și rămâne după repornire | — | Manual |
| T-12 | Interval de refresh | Setează Email la 30 s | Lista se actualizează la ~30 s (verificat în telemetrie) | — | Manual |
| T-13 | Mod offline | Deconectează Wi-Fi/Ethernet în timpul rulării | Fără erori pe ecran; bara de stare trece pe Offline; widget-urile arată „Offline · acum X min”; UI-ul rămâne interactiv | C3 | Manual |
| T-14 | Revenire online | Reconectează rețeaua | Datele se resincronizează singure; indicatorul revine pe Online | C3 | Manual |
| T-15 | Prima pornire fără internet | Golește cache-ul, pornește fără rețea | „Date indisponibile — se reîncearcă automat”, fără crash | C3 | Auto |
| T-16 | Sursă externă căzută | Forțează adaptorul pe timeout, 500 și 429 | Se servesc datele din cache cu `is_stale = true`; backoff respectat | C3 | Auto |
| T-17 | PIN greșit și blocare | Introdu de 5 ori un PIN greșit | Mesajele de încercări rămase, apoi blocare cu numărătoare inversă | C4 | Auto + Manual |
| T-18 | Blocare automată | Nu atinge ecranul `auto_lock_minutes` | Sesiunea se blochează; previzualizarea deschisă se închide | C4 | Manual |
| T-19 | Fără secrete în Git | Caută în repo PIN, parole, chei | Niciun secret; doar `.env.example` fără valori | C4 | Auto (CI) |
| T-20 | Conținut periculos | Email / știre cu `<script>` sau HTML în text | Se afișează ca text, nu se execută | C4 | Auto |
| T-21 | Panou Sistem | Rulează 5 min pe placă | Temperatura, CPU și RAM se schimbă în timp real și corespund cu `vcgencmd` / `htop` | C4 | Manual |
| T-22 | Latență sursă vs. cache | ≥ 50 de cereri pe fiecare sursă | Tabel cu latența medie live vs. din cache | C4 | Auto (script) |
| T-23 | Răspuns la atingere | Măsoară răspunsul vizual pe butoane și liste | Sub 150 ms | — | Manual |
| T-24 | Rulare de durată | 60 min continuu pe placa #2 | Fără creștere constantă a memoriei; temperatura stabilă | — | Manual |

## 10. Întrebări deschise

| ID | Întrebare | Cine răspunde | Până când |
|---|---|---|---|
| Î1 | Ce rezoluție are touchscreen-ul plăcii #2 și e orientat pe orizontală sau pe verticală? | DEVOPS | cât mai repede — blochează layout-ul FE-1 |
| Î2 | Emailul universitar permite IMAP sau OAuth2? Dacă nu, demo-ul se face în modul Mock. | MAIL-1 | 10 nov. |
| Î3 | Ce fluxuri RSS reale folosim ca surse implicite (3–4)? | DATA-WN | Sprint 1 |
| Î4 | Ce PIN implicit se configurează în `.env.example` pentru demo? | SEC / TL | Sprint 2 |

## Istoric

| Data | Versiune | Modificare |
|---|---|---|
| 10 nov. 2026 | 1.0 | Versiunea inițială, aliniată pe contractul v1.0.0 |
