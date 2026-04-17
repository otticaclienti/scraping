# Email Scraper

Tool per estrarre email da liste di siti web. Carichi un file di URL, il crawler
visita ogni sito (homepage + pagine contatti + sitemap), estrae le email anche
da pattern offuscati, e salva tutto in Postgres. UI Streamlit per controllo
completo (avvio, pausa, stop, retry, export CSV, blacklist).

## Stack

- **Backend**: FastAPI + SQLAlchemy async + Postgres
- **Worker**: ARQ (Redis) con fan-out asincrono, concorrenza configurabile
- **Crawler**: httpx async + Playwright come fallback per pagine JS-heavy
- **Frontend**: Streamlit multipagina
- **Deploy**: Docker Compose

## Avvio

```bash
docker compose up --build
```

- UI: http://localhost:8501
- API: http://localhost:8000 (OpenAPI su `/docs`)

Il primo avvio scarica Playwright/Chromium: può richiedere qualche minuto.

## Uso

1. Apri http://localhost:8501 → **Nuovo Job**
2. Carica un `.txt` o `.csv` con un URL per riga (oppure incolla gli URL)
3. Regola concorrenza, timeout, pagine max, fallback JS, verifica MX
4. Avvia. Vai su **Dettaglio Job** per progress live e controlli
5. **Email** → sfoglia/cerca/esporta CSV

### Formato lista

Un URL per riga. Commenti con `#`. Schema opzionale (`http://` aggiunto se mancante).

```
https://example.com
altrosito.it
# questa riga è ignorata
```

## Cosa estrae

- `mailto:` links
- Email nel testo (regex RFC-lite)
- Offuscamenti comuni: `[at]`, `(at)`, `[dot]`, ` at `, ` dot `, entity HTML (`&#64;`)
- Cloudflare email protection (`data-cfemail`)
- Con fallback JS attivo: email generate via JavaScript

Pagine visitate per sito:
- Homepage
- `/contatti`, `/contact`, `/about`, `/chi-siamo`, `/team`, `/staff`, `/imprint`, `/privacy`, ...
- Link interni con parole chiave (contact/about/team/...)
- `sitemap.xml` / `sitemap_index.xml` (opzionale)

## Configurazione per job

| Parametro | Default | Range |
|---|---|---|
| concurrency | 50 | 1–500 |
| timeout_seconds | 15 | 3–120 |
| max_pages_per_site | 8 | 1–50 |
| max_attempts | 2 | 1–5 |
| render_js_fallback | true | bool |
| verify_mx | false | bool |
| follow_sitemap | true | bool |
| user_agent | (default UA) | str |

## Performance indicativa

Per 10.000 siti con concorrenza 50:
- Solo HTTP: ~30–60 min
- Con Playwright fallback attivo: ~2–4 ore (Playwright si attiva solo se HTTP non trova nulla)

## Note legali

L'utilizzo di dati personali (email aziendali incluse, in UE) è soggetto a GDPR.
Assicurati di avere una base giuridica valida per trattare e contattare gli indirizzi
raccolti. Rispetta `robots.txt` dei siti target se lo richiedono.

## Sviluppo locale (senza Docker)

```bash
# terminal 1: postgres + redis
docker compose up postgres redis

# terminal 2: backend
cd backend
pip install -r requirements.txt
playwright install chromium
DATABASE_URL=postgresql+asyncpg://scraper:scraper@localhost:5432/scraper \
REDIS_URL=redis://localhost:6379/0 \
uvicorn app.main:app --reload

# terminal 3: worker
cd backend
DATABASE_URL=postgresql+asyncpg://scraper:scraper@localhost:5432/scraper \
REDIS_URL=redis://localhost:6379/0 \
arq app.worker.WorkerSettings

# terminal 4: frontend
cd frontend
pip install -r requirements.txt
BACKEND_URL=http://localhost:8000 streamlit run app.py
```

## Struttura

```
backend/
  app/
    main.py              # FastAPI app
    config.py            # Settings (pydantic-settings)
    db.py                # SQLAlchemy async engine
    models.py            # Job, Site, Email, BlacklistDomain
    schemas.py           # Pydantic DTOs
    queue.py             # ARQ pool
    worker.py            # ARQ WorkerSettings + scrape_job task
    api/
      jobs.py            # /jobs CRUD + controlli + export CSV
      emails.py          # /emails list/search/count
      blacklist.py       # /blacklist
    scraper/
      fetcher.py         # HttpFetcher + PlaywrightFetcher
      extractor.py       # Regex + deobfuscation + Cloudflare
      validator.py       # Syntax + MX record
      crawler.py         # crawl_site: orchestrazione per-sito
frontend/
  app.py                 # Home dashboard
  api_client.py          # httpx client verso backend
  pages/
    1_Nuovo_Job.py
    2_Dettaglio_Job.py
    3_Email.py
    4_Blacklist.py
docker-compose.yml
```
