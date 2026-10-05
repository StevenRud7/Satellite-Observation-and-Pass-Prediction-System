# INSTRUCTIONS — Run, Test, and Troubleshoot Everything Locally

This is the complete guide to running the **Satellite Observation & Pass
Prediction System** on your own machine: backend, frontend, database
(with Docker), data loading, tests, and a large troubleshooting section.

Commands are given for **Windows PowerShell** first (the most common
setup for this project), with **cmd** and **macOS / Linux** equivalents
wherever they differ.

## Table of contents

1. [What you are running](#1-what-you-are-running)
2. [Prerequisites](#2-prerequisites)
3. [Quick start (3 terminals)](#3-quick-start-3-terminals)
4. [Database and data setup (Docker)](#4-database-and-data-setup-docker)
5. [Backend in detail](#5-backend-in-detail)
6. [Frontend in detail](#6-frontend-in-detail)
7. [Using the app end to end](#7-using-the-app-end-to-end)
8. [Testing everything](#8-testing-everything)
9. [Python version compatibility](#9-python-version-compatibility)
10. [Troubleshooting](#10-troubleshooting)
11. [Reset / clean-slate recipes](#11-reset--clean-slate-recipes)
12. [Command cheat sheet](#12-command-cheat-sheet)

---

## 1. What you are running

```text
Browser  ──►  Frontend (Vite dev server, :5173)
                  │  fetch()  (VITE_API_BASE_URL)
                  ▼
              Backend (FastAPI/uvicorn, :8000)  ──►  CelesTrak (real orbital data, on demand)
                  │
                  ▼  (optional, but needed for persistence)
              PostgreSQL (Docker, :5432)
```

| Piece | Port | Needs |
|---|---|---|
| Backend API | `8000` | Python 3.8–3.12 |
| Frontend | `5173` | Node.js 18+ |
| PostgreSQL | `5432` | Docker Desktop (or a native Postgres install) |

**The database is optional for a first run.** Without `DATABASE_URL` the
backend runs fully, using an in-memory satellite cache. The database is
needed for: satellite data surviving a restart, saved observer locations,
and stored passes/visibility predictions. See [section 4](#4-database-and-data-setup-docker).

---

## 2. Prerequisites

| Tool | Version | Check with | Notes |
|---|---|---|---|
| Python | **3.8 – 3.12** (3.11 recommended) | `python --version` | 3.8 is end-of-life but supported; see [section 9](#9-python-version-compatibility) |
| Node.js | **18+** (20 or 22 LTS recommended) | `node --version` | Comes with `npm` |
| npm | 9+ | `npm --version` | |
| Docker Desktop | any recent | `docker --version` and `docker compose version` | Only for the local database |
| Git | any | `git --version` | Optional |

**Windows: several Pythons installed?** List them with the launcher:

```powershell
py -0p
```

and create the virtual environment with the one you want, e.g.
`py -3.11 -m venv .venv` (section 5).

**Internet access is required at runtime** for `https://celestrak.org`
(orbital data is fetched on demand), and once at install time for `pip`
and `npm`.

---

## 3. Quick start (3 terminals)

Everything below assumes you are in the project root (the folder
containing `backend/`, `frontend/`, and `docker-compose.yml`) unless a
step says otherwise.

### 3.1 The three terminals, at a glance

| Terminal | Runs | Stays open while you use the site? |
|---|---|---|
| 1 — Database | `docker compose` (Postgres in Docker) | Yes - or just leave Docker Desktop running; see 3.5 |
| 2 — Backend | the Python/FastAPI API (`uvicorn`) | Yes |
| 3 — Frontend | the Vite dev server (`npm run dev`) | Yes |

You need all three running **at the same time** to use the full site.
Terminal 1 (the database) is optional - see [section 4.2](#42-option-a--no-database-simplest)
if you'd rather skip it for now.

Every command below is tagged so you know whether you'll ever need to
type it again:

| Tag | Meaning |
|---|---|
| 🟩 **ONCE EVER** | Do this the first time you set the project up on this machine. Never needed again, unless you delete what it created (a fresh clone, a deleted `.venv`/`node_modules`, a wiped Docker volume) or the project's dependencies change (see [section 11](#11-reset--clean-slate-recipes)). |
| 🟦 **EVERY TIME YOU START** | Type this whenever you sit down to run the site - whether the terminal is one you just opened, or one that's been open the whole time. |
| 🟨 **ONLY IF YOU CLOSED THE TERMINAL** | Skip this if the terminal window/tab has been open since you last ran the site (e.g. you only pressed Ctrl+C to stop `uvicorn`, but never closed the window). Only needed after closing the terminal, restarting your computer, or opening a brand new terminal. |

### 3.2 Terminal 1 — Database

```powershell
docker compose up -d
```
🟦 **EVERY TIME YOU START** (safe to run even if it's already running - it just confirms the container is up; nothing to redo here after closing a terminal, since Docker Desktop keeps the container running independently of any particular terminal window).

Expected output the first time (creates things):
```text
[+] Running 2/2
 ✔ Network satellite-obs-system_default       Created
 ✔ Container satellite-obs-system-postgres-1  Started
```
Expected output on later runs (container already exists):
```text
[+] Running 1/1
 ✔ Container satellite-obs-system-postgres-1  Started
```
(The exact network/container name depends on the folder name you extracted the project into - "something-postgres-1" either way.)

You do not need to keep this terminal open at all for Docker itself to
keep running - `docker compose up -d` starts the container in the
background (the `-d` is "detached") and it keeps running even if you
close the terminal, as long as Docker Desktop is running. Opening this
terminal again later and re-running the same command is enough; see
[section 4.4](#44-everyday-docker-commands) for `logs`/`ps`/`stop`.

### 3.3 Terminal 2 — Backend

**First time only** (🟩 ONCE EVER):
```powershell
cd backend
py -3.11 -m venv .venv            # or: python -m venv .venv
```
```powershell
.\.venv\Scripts\Activate.ps1      # cmd: .venv\Scripts\activate.bat   |  macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```
Expected output ends with something like:
```text
Successfully installed fastapi-... pydantic-... sqlalchemy-... sgp4-... astropy-... numpy-... ...
```
```powershell
copy .env.example .env            # macOS/Linux: cp .env.example .env
```
Now edit `backend\.env` in a text editor. If you started the database in
Terminal 1, set:
```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/satellite_obs
```
Then, still in Terminal 2, with the venv active:
```powershell
alembic upgrade head               # only if DATABASE_URL is set
```
Expected output ends with:
```text
Running upgrade  -> d258f3b52216, initial schema
Running upgrade d258f3b52216 -> ae89107ca46d, add index on passes observer_id and rise_time
```

**Every time you start the site** (🟦 EVERY TIME YOU START), continuing in
the same terminal:
```powershell
uvicorn app.main:app --reload
```
Expected output ends with:
```text
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [...] using WatchFiles
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```
Leave this running - this terminal is now "the backend". Open
**http://localhost:8000/docs** to confirm.

**If you closed this terminal and are reopening it** (🟨 ONLY IF YOU CLOSED
THE TERMINAL), do these two lines *before* `uvicorn app.main:app --reload`
above - nothing else from the first-time block needs repeating:
```powershell
cd backend
.\.venv\Scripts\Activate.ps1      # cmd: .venv\Scripts\activate.bat   |  macOS/Linux: source .venv/bin/activate
```
Your prompt should show `(.venv)` again before you run `uvicorn`.

### 3.4 Terminal 3 — Frontend

**First time only** (🟩 ONCE EVER):
```powershell
cd frontend
copy .env.example .env.local      # macOS/Linux: cp .env.example .env.local
npm install
```
Expected output ends with something like:
```text
added 350 packages in 8s
```

**Every time you start the site** (🟦 EVERY TIME YOU START), continuing in
the same terminal:
```powershell
npm run dev
```
Expected output:
```text
  VITE v5.4.21  ready in 400 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```
Leave this running too, then open **http://localhost:5173**.

**If you closed this terminal and are reopening it** (🟨 ONLY IF YOU CLOSED
THE TERMINAL), do this one line first - there is no virtual environment to
reactivate on the frontend side, you just need to be in the right folder:
```powershell
cd frontend
```
then `npm run dev` as above.

### 3.5 Putting it together

| Situation | Terminal 1 (DB) | Terminal 2 (Backend) | Terminal 3 (Frontend) |
|---|---|---|---|
| Very first time | full 3.2 | full 3.3 first-time block, then `uvicorn ...` | full 3.4 first-time block, then `npm run dev` |
| Same terminals, you just pressed Ctrl+C to stop the backend/frontend | `docker compose up -d` (harmless if already up) | just `uvicorn app.main:app --reload` again | just `npm run dev` again |
| You closed the terminal windows / restarted your computer | `docker compose up -d` | `cd backend` → activate venv → `uvicorn app.main:app --reload` | `cd frontend` → `npm run dev` |
| You pulled/edited backend code that changed `requirements.txt`, or ran a new migration | - | re-run `pip install -r requirements.txt` and/or `alembic upgrade head`, then `uvicorn ...` | - |
| You edited `frontend/package.json` | - | - | re-run `npm install`, then `npm run dev` |

Once all three are running, open **http://localhost:5173**. The header
should show **Backend status: Online**. If it doesn't, or nothing loads,
jump to [section 10.2](#102-backend-startup-and-configuration) and
[10.6](#106-frontend).

> Every backend command must be run from the `backend/` folder with the
> virtual environment active (`(.venv)` visible in your prompt). Running
> from the wrong folder is the #1 cause of `ModuleNotFoundError: No
> module named 'app'` and of `.env` not being read (see
> [troubleshooting](#10-troubleshooting)).

---

## 4. Database and data setup (Docker)

### 4.1 How data gets into the system (read this first)

There is **no bulk import step** — you do not have to load a catalog.
Orbital data flows like this:

```text
You (or the UI) request a satellite by NORAD ID, e.g. 25544 (ISS)
        │
        ▼
Backend checks its cache ── fresh (younger than the TTL)? ──► use it
        │ stale or missing
        ▼
Backend fetches that one satellite from CelesTrak, validates the TLE,
stores it in the cache, and returns it
```

- The cache is **PostgreSQL** if `DATABASE_URL` is set, otherwise an
  **in-memory** cache that is lost on restart.
- The freshness window is `ORBITAL_DATA_CACHE_TTL_SECONDS` (default
  `21600` = 6 hours). CelesTrak only updates its data a few times per
  day, so re-fetching more often is pointless and can get you blocked
  (see troubleshooting: *CelesTrak returned HTTP 403*).
- `GET /api/satellites/{norad_id}?refresh=true` forces a re-fetch.
- `GET /api/satellites` lists satellites **already cached** — it will be
  empty (`[]`) until you have requested at least one satellite.
- Default satellite for ranking is the ISS (`25544`). The UI lets you add
  more by NORAD ID. A full-catalog browser is a documented limitation
  (see `LIMITATIONS.md`).

### 4.2 Option A — no database (simplest)

Leave `DATABASE_URL=` empty in `backend/.env`. Skip everything else in
section 4. Predictions and ranking work; saving observers, storing
passes, and cache persistence do **not** (those endpoints return
`503 ... requires a database`).

### 4.3 Option B — PostgreSQL in Docker (recommended)

The repository ships a `docker-compose.yml` that starts PostgreSQL 16:

| Setting | Value |
|---|---|
| Image | `postgres:16` |
| User / password | `postgres` / `postgres` |
| Database | `satellite_obs` |
| Port | `5432` on your machine |
| Data volume | `postgres_data` (survives container restarts) |

These credentials are for **local development only** — never reuse them
anywhere real.

**Step 1 — Start Docker Desktop** and wait until it says it is running
(Windows: it needs WSL 2; see troubleshooting if it will not start).

**Step 2 — Start the database** (from the project root):

```powershell
docker compose up -d
docker compose ps
```

`STATE` should be `running`. To watch logs (Ctrl+C to stop watching):

```powershell
docker compose logs -f postgres
```

Wait for `database system is ready to accept connections`.

**Step 3 — Point the backend at it.** In `backend/.env`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/satellite_obs
```

The scheme **must** be `postgresql+psycopg://` (this project uses the
psycopg 3 driver). `postgresql://` or `postgres://` will not work.

**Step 4 — Create the tables with Alembic** (from `backend/`, venv active):

```powershell
alembic upgrade head
```

Expected output ends with two lines:

```text
Running upgrade  -> d258f3b52216, initial schema
Running upgrade d258f3b52216 -> ae89107ca46d, add index on passes observer_id and rise_time
```

Verify:

```powershell
alembic current                                   # -> ae89107ca46d (head)
docker compose exec postgres psql -U postgres -d satellite_obs -c "\dt"
```

You should see these tables: `alembic_version`, `observers`, `orbital_elements`,
`passes`, `satellites`, `visibility_predictions`.

**Step 5 — Create a separate database for the tests** (important — see
the warning in [section 8.1](#81-backend-tests)):

```powershell
docker compose exec postgres psql -U postgres -c "CREATE DATABASE satellite_obs_test;"
```

**Step 6 — Load some real data** (start the backend first, see section 5):

```powershell
# PowerShell
Invoke-RestMethod http://localhost:8000/api/satellites/25544 | ConvertTo-Json -Depth 6
# cmd / macOS / Linux / Git Bash
curl http://localhost:8000/api/satellites/25544
```

The first call fetches the ISS from CelesTrak and stores it; later calls
within 6 hours are served from the database. Confirm it was stored:

```powershell
docker compose exec postgres psql -U postgres -d satellite_obs -c "SELECT norad_id, name FROM satellites;"
```

### 4.4 Everyday Docker commands

| Goal | Command |
|---|---|
| Start database | `docker compose up -d` |
| Stop (keeps data) | `docker compose stop` |
| Stop and remove container (keeps data volume) | `docker compose down` |
| **Delete all database data** | `docker compose down -v` |
| Open a SQL shell | `docker compose exec postgres psql -U postgres -d satellite_obs` |
| Show logs | `docker compose logs -f postgres` |
| Is it running? | `docker compose ps` |

Inside `psql`: `\dt` lists tables, `\d observers` describes one, `\q`
quits.

You can also connect a GUI client (DBeaver, pgAdmin, TablePlus) with
host `localhost`, port `5432`, user `postgres`, password `postgres`,
database `satellite_obs`.

### 4.5 Option C — native PostgreSQL (no Docker)

Install PostgreSQL 14+ for your OS, then create the databases (the
`psql` prompt is `postgres=#`):

```sql
CREATE DATABASE satellite_obs;
CREATE DATABASE satellite_obs_test;
```

Use the same `DATABASE_URL` format with your own user/password/port:
`postgresql+psycopg://USER:PASSWORD@localhost:5432/satellite_obs`.
If your password contains special characters (`@ : / # %`),
URL-encode them (`@` → `%40`).

### 4.6 Option D — hosted Postgres (Neon)

Use the connection string Neon gives you and change its scheme to
`postgresql+psycopg://`, keeping `?sslmode=require`. See `DEPLOYMENT.md`
for the production walkthrough. **Never run `pytest` against it.**

### 4.7 Migration commands you may need

Run from `backend/` with `DATABASE_URL` set:

| Goal | Command |
|---|---|
| Apply all migrations | `alembic upgrade head` |
| Show current revision | `alembic current` |
| Show history | `alembic history --verbose` |
| Undo the last migration | `alembic downgrade -1` |
| Undo everything | `alembic downgrade base` |
| Create a migration after changing a model | `alembic revision --autogenerate -m "describe change"` (always review the generated file) |

---

## 5. Backend in detail

All commands from the `backend/` folder.

### 5.1 Create and activate a virtual environment

Using a virtual environment keeps this project's pinned library versions
from clashing with other Python projects on your machine.

```powershell
# PowerShell
py -3.11 -m venv .venv        # pick any of 3.8-3.12 that you have; `python -m venv .venv` also works
.\.venv\Scripts\Activate.ps1
```

```bat
:: cmd
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now start with `(.venv)`. Confirm you are using the
venv's Python:

```powershell
python --version
where.exe python        # macOS/Linux: which python   -> must point inside .venv
```

If PowerShell refuses to run the activation script, see
[troubleshooting](#10-troubleshooting) ("running scripts is disabled").

### 5.2 Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` picks compatible **astropy/numpy** versions
automatically based on your Python version (via environment markers):

| Python | astropy | numpy |
|---|---|---|
| 3.8, 3.9 | 5.2.2 | 1.24.4 |
| 3.10 – 3.12 | 6.1.4 | 2.1.1 |

You do not need to edit anything. Check what was installed:

```powershell
pip list | findstr /i "numpy astropy sgp4 fastapi pydantic sqlalchemy"      # macOS/Linux: pip list | grep -iE "..."
```

### 5.3 Configure environment variables

```powershell
copy .env.example .env         # macOS/Linux: cp .env.example .env
```

`backend/.env` is git-ignored. Variables:

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated origins allowed to call the API |
| `DATABASE_URL` | *(empty)* | `postgresql+psycopg://user:pass@host:5432/db`; empty = in-memory cache, no persistence |
| `ORBITAL_DATA_CACHE_TTL_SECONDS` | `21600` | How long a fetched satellite stays fresh (commented out in `.env.example`) |

Notes:
- The `.env` file is read **relative to the folder you launch from**
  (`backend/`). Launching from elsewhere silently ignores it.
- A real environment variable **overrides** `.env`. If behavior does not
  match your `.env`, check for a leftover variable:
  `echo $env:DATABASE_URL` (PowerShell) / `echo %DATABASE_URL%` (cmd).
- Opening the frontend as `http://127.0.0.1:5173` instead of
  `http://localhost:5173` is a *different origin* and will be blocked by
  CORS unless you list it too:
  `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`.
- Restart the backend after editing `.env`.

### 5.4 Run the API

```powershell
uvicorn app.main:app --reload
```

`--reload` restarts the server when you edit code (development only).
Useful variants:

```powershell
uvicorn app.main:app --reload --port 8001          # different port
uvicorn app.main:app --host 0.0.0.0 --port 8000    # reachable from other devices on your LAN
python -m uvicorn app.main:app --reload            # if `uvicorn` is "not recognized"
```

You should see `Application startup complete.` and log lines showing your
environment and CORS origins.

### 5.5 Verify the backend

```powershell
Invoke-RestMethod http://localhost:8000/health          # PowerShell
curl http://localhost:8000/health                        # cmd / macOS / Linux
```

Expected:

```json
{"status":"ok","service":"satellite-observation-api","timestamp":"2026-..."}
```

Then open **http://localhost:8000/docs** — interactive Swagger UI where
you can try every endpoint from the browser (`/redoc` is an alternative
view).

### 5.6 API smoke tests

The examples use Tel Aviv (32.0853, 34.7818, 20 m) and the ISS (25544).
Replace them with your own values. In **PowerShell 5**, `curl` is an alias
for `Invoke-WebRequest`; use `curl.exe` or `Invoke-RestMethod` instead.

| What | Command |
|---|---|
| Satellite record | `curl.exe "http://localhost:8000/api/satellites/25544"` |
| Force re-fetch | `curl.exe "http://localhost:8000/api/satellites/25544?refresh=true"` |
| Cached satellites (needs DB) | `curl.exe "http://localhost:8000/api/satellites"` |
| Next pass (live, not stored) | `curl.exe "http://localhost:8000/api/passes/next?norad_id=25544&latitude_deg=32.0853&longitude_deg=34.7818&altitude_m=20"` |
| Ranked best opportunities | `curl.exe "http://localhost:8000/api/observations/best?latitude_deg=32.0853&longitude_deg=34.7818&method=naked_eye&within_hours=48&norad_ids=25544"` |

`method` is `naked_eye`, `binoculars`, or `telescope`. `within_hours` is
up to 336 (14 days).

Saving and listing observers (needs the database). PowerShell:

```powershell
$body = '{"name":"Tel Aviv","latitude_deg":32.0853,"longitude_deg":34.7818,"altitude_m":20}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/observers -ContentType "application/json" -Body $body
Invoke-RestMethod http://localhost:8000/api/observers
Invoke-RestMethod -Method Delete http://localhost:8000/api/observers/1
```

macOS / Linux / Git Bash:

```bash
curl -X POST http://localhost:8000/api/observers -H "Content-Type: application/json" \
     -d '{"name":"Tel Aviv","latitude_deg":32.0853,"longitude_deg":34.7818,"altitude_m":20}'
```

Predict-and-store passes (needs the database) — easiest from the
`/docs` page: `POST /api/passes/predict` with

```json
{
  "norad_id": 25544,
  "latitude_deg": 32.0853,
  "longitude_deg": 34.7818,
  "altitude_m": 20,
  "start": "2026-09-25T00:00:00Z",
  "end": "2026-09-26T00:00:00Z"
}
```

Use dates in the near future. Provide **either** `observer_id` **or**
`latitude_deg` + `longitude_deg`, never both.

HTTP status codes you may see:

| Code | Meaning |
|---|---|
| 200 / 201 / 204 | Success / created / deleted |
| 404 | Satellite, observer, or pass not found (also: no pass in the window for `/passes/next`) |
| 409 | Data was expected in the cache but is not there |
| 422 | Invalid input (e.g. latitude outside −90..90) or invalid orbital data |
| 502 | CelesTrak could not be reached or returned an error |
| 503 | Feature needs a database but `DATABASE_URL` is not set |

---

## 6. Frontend in detail

All commands from the `frontend/` folder.

### 6.1 Install

```powershell
npm install        # or: npm ci   (exact versions from package-lock.json; best for a clean, reproducible install)
```

### 6.2 Configure the API URL

```powershell
copy .env.example .env.local     # macOS/Linux: cp .env.example .env.local
```

`frontend/.env.local` (git-ignored) contains:

```env
VITE_API_BASE_URL=http://localhost:8000
```

- Only variables starting with `VITE_` reach browser code.
- **Vite reads this file only when the dev server starts.** After editing
  it, stop (`Ctrl+C`) and re-run `npm run dev`.
- If the backend runs on another port, change this to match.
- Never put secrets here; everything in the frontend is visible to users.

### 6.3 Run

```powershell
npm run dev
```

Open **http://localhost:5173**.

### 6.4 Other frontend commands

| Goal | Command |
|---|---|
| Unit tests (once) | `npm test` |
| Unit tests (watch mode) | `npm run test:watch` |
| Lint | `npm run lint` |
| Check formatting | `npm run format:check` |
| Auto-format | `npm run format` |
| Type-check + production build | `npm run build` (output in `dist/`) |
| Serve the production build locally | `npm run preview` (after `npm run build`) |

`npm run build` prints a warning that some chunks are larger than 500 kB
(`three`, `recharts`). That is expected and harmless.

For a production build against a deployed API, see
`frontend/.env.production.example` and `DEPLOYMENT.md`.

---

## 7. Using the app end to end

1. Start backend and frontend. Confirm **Backend status: Online**.
2. **Your location** — enter latitude, longitude, altitude (metres), and
   optionally a name. Longitude is negative for the western hemisphere.
   *Save this location* stores it (needs the database); it then appears in
   the saved-locations dropdown.
3. **Satellites to consider** — the ISS is preselected. Add more by
   entering a NORAD ID (e.g. `25544` for the ISS, `20580` for the Hubble
   Space Telescope; look up other IDs at celestrak.org) and clicking
   **Add**. This looks the satellite up on CelesTrak.
4. **Observation preferences** — choose **Naked Eye / Binoculars /
   Telescope**, a time window (**Tonight / Next 24 hours / Next 3 days**),
   and a minimum elevation.
5. Click **Find best opportunities**. The first request per satellite is
   slower because it fetches fresh data from CelesTrak.
6. Click a result to open the **pass detail** page: rise / peak / set,
   duration, closest range, the three method scores, and a **Why**
   explanation.
7. Use the tabs **Sky Path**, **3D View**, and **Elevation Graph**.

"No opportunities found" is a normal result: satellites are only
observable when they are above your horizon **and** you are in darkness
**and** the satellite is sunlit. Try **Next 3 days**, a lower minimum
elevation, or more satellites.

Remember: the score is a **heuristic ranking**, not a probability, and it
ignores clouds and local obstructions (see `LIMITATIONS.md`).

---

## 8. Testing everything

### 8.1 Backend tests

⚠️ **Read before running:** the database tests **create and drop every
table and truncate data** in whatever database `DATABASE_URL` points to.
Never run `pytest` with `DATABASE_URL` pointing at your development
database (`satellite_obs`) or at Neon. Use the dedicated
`satellite_obs_test` database from section 4.3 step 5.

**Option 1 — without a database.** Run with `DATABASE_URL` empty/unset.
The ~64 database-backed tests are *skipped* (not failed):

```powershell
cd backend
pytest
```

**Option 2 — everything, including database tests** (recommended before
you commit). Set `DATABASE_URL` for that one shell only:

```powershell
# PowerShell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/satellite_obs_test"
pytest
Remove-Item Env:DATABASE_URL          # unset it again afterwards
```

```bat
:: cmd
set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/satellite_obs_test
pytest
set DATABASE_URL=
```

```bash
# macOS / Linux
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/satellite_obs_test pytest
```

(A real environment variable overrides `backend/.env`, so this is safe
even if your `.env` points at the dev database.)

Expected result (at the time of writing):

| Mode | Result |
|---|---|
| No database | `145 passed, 64 skipped` |
| With test database | `209 passed` |

You will also see a coverage table (about 85% overall) and, on Python 3.8,
`AstropyWarning` messages about IERS data — those are harmless (see
troubleshooting).

Useful variations:

```powershell
pytest --no-cov                           # faster, no coverage report
pytest -x                                 # stop at first failure
pytest -v                                 # verbose: one line per test
pytest tests/test_passes.py               # one file
pytest tests/test_passes.py::test_name    # one test
pytest -k "visibility"                    # tests whose name matches
pytest --cov-report=html                  # then open htmlcov/index.html
pytest -rs                                # show why tests were skipped
```

What the tests do **not** need: internet access. CelesTrak is mocked, so
the suite is deterministic and works offline.

### 8.2 Backend lint, format, and type checks

```powershell
ruff check .            # lint      (ruff check --fix . to auto-fix)
black --check .         # formatting (black . to auto-format)
mypy app                # static type check
```

All three should report no problems.

### 8.3 Frontend tests and checks

```powershell
cd frontend
npm test                # 11 tests at time of writing
npm run lint
npm run format:check
npm run build           # includes TypeScript type checking
```

### 8.4 Full "is everything healthy?" checklist

Run this before committing or opening a pull request:

```powershell
# Backend  (from backend/, venv active, DATABASE_URL -> the *test* database)
ruff check . ; black --check . ; mypy app ; pytest --no-cov
# Frontend (from frontend/)
npm run lint ; npm run format:check ; npm test ; npm run build
```

(In cmd, chain with `&&` instead of `;`.)

### 8.5 Manual smoke test

1. `GET /health` returns `"status":"ok"`.
2. `/docs` loads.
3. `GET /api/satellites/25544` returns the ISS with TLE lines and an epoch.
4. `GET /api/passes/next?...` returns a pass (or a clear 404 if none).
5. In the UI: enter a location, click **Find best opportunities**, open a
   result, and check all three tabs render.

---

## 9. Python version compatibility

The backend supports **Python 3.8 through 3.12**.

Why this section exists: earlier versions of the code used Python 3.10+
syntax (`str | None`, `datetime.UTC`, `zip(strict=True)`), which crashed
on Python 3.8 with errors like
`TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'` and
`Could not resolve all types within mapped annotation: "Mapped[str | None]"`.
Pydantic and SQLAlchemy evaluate annotations at runtime, so on 3.8/3.9
`str | None` and `list[str]` are invalid. The code now uses
`typing.Optional`, `typing.List`, and `timezone.utc`.

Rules for writing new backend code so it stays compatible:

- Use `Optional[X]` / `Union[X, Y]`, not `X | Y`.
- Use `List`, `Dict`, `Tuple`, ... from `typing`, not `list[...]`.
- Use `datetime.now(timezone.utc)`, not `datetime.UTC`.
- Do not use `zip(strict=...)`, `match` statements, or `functools.cache`.

`tests/test_python_compat.py` scans the source and fails with file and
line numbers if any of these creep back in (this protects you when
developing on Python 3.11+, where the mistake would otherwise go
unnoticed). `ruff` is configured with `keep-runtime-typing = true` so it
will not "modernize" these back.

If you decide to drop Python 3.8/3.9 support later, delete that test, set
`keep-runtime-typing` to `false`, and update this section.

Python 3.8 reached end of life in October 2024 and its pinned libraries
(numpy 1.24, astropy 5.2) no longer receive updates. It works, but
**Python 3.11 is recommended** for anything long-lived.

Verified on Python 3.8, 3.11, and 3.12 (backend tests, lint, type checks,
migrations, and server startup).

---

## 10. Troubleshooting

Find your symptom, then apply the fix. Errors are grouped by area.

### 10.1 Python, virtual environments, and installs

**`TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`**
or **`Could not resolve all types within mapped annotation: "Mapped[str | None]"`**
→ You are on Python 3.8/3.9 with code that uses 3.10+ syntax. Current
code already fixes this ([section 9](#9-python-version-compatibility)).
If you still see it, you are running an **old copy** of the project:
re-extract the latest zip, or check which folder your terminal is in.
Also confirm `python --version` and that the venv is active.

**`ImportError: cannot import name 'UTC' from 'datetime'`** → same cause
(Python < 3.11 with old code). Use the current code.

**`pip install -r requirements.txt` fails on astropy/numpy** (e.g.
"No matching distribution found", "requires a different Python", or a
build error) → your Python is not in 3.8–3.12, or is too new. Run
`python --version`. Python 3.13+ is not yet supported by the pinned
astropy/numpy. Create the venv with a supported version:
`py -3.11 -m venv .venv`.

**Build error mentioning `Microsoft Visual C++ 14.0 or greater is required`**
→ a package tried to compile from source because no prebuilt wheel exists
for your Python/OS. First upgrade pip (`python -m pip install --upgrade pip`)
and use a supported Python version (3.8–3.12, 64-bit). If it persists,
install "Microsoft C++ Build Tools" and retry.

**`ModuleNotFoundError: No module named 'app'`** → you are not in
`backend/`. `cd backend`, then retry.

**`ModuleNotFoundError: No module named 'fastapi'` (or `sqlalchemy`,
`sgp4`, ...)** → the venv is not active or dependencies are not installed
into it. Activate it (`(.venv)` in the prompt) and run
`pip install -r requirements.txt`. Confirm with `where.exe python`.

**`'uvicorn' is not recognized...` / `'pytest' is not recognized...`** →
the venv is not active. Activate it, or run through Python:
`python -m uvicorn app.main:app --reload`, `python -m pytest`.

**PowerShell: `running scripts is disabled on this system`** when
activating the venv →

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

then activate again. Or use cmd and `.venv\Scripts\activate.bat`.

**`python` opens the Microsoft Store (Windows)** → disable the "App
execution aliases" for python in *Settings → Apps → Advanced app
settings*, or use the launcher: `py -3.11`.

**Wrong Python picked up / packages installed globally** → always create
and activate a venv. Check with `pip --version` (path must be inside
`.venv`).

**`mypy` says "Pattern matching is only supported in Python 3.10 and
greater"** → an old `pyproject.toml` pinned `python_version` in the mypy
settings. The current file does not; re-extract the latest project.

**`AstropyWarning: Tried to get polar motions for times after IERS data is
valid` / `(some) times are outside of range covered by IERS table`** →
harmless. Astropy uses an Earth-orientation table that is bundled with
the installed version and tries to download a newer one; if you are
offline or the bundled table is old, it falls back to a slightly less
precise value (arcsecond-level, irrelevant for pass prediction). Tests
still pass.

### 10.2 Backend startup and configuration

**Server starts, but the frontend says Offline** → check
`http://localhost:8000/health` in the browser. If that works, see the CORS
and `VITE_API_BASE_URL` entries in 10.6.

**`Address already in use` / `[Errno 10048]` on port 8000** → something
already uses that port (often an old uvicorn still running).

```powershell
netstat -ano | findstr :8000          # macOS/Linux: lsof -i :8000
taskkill /PID <pid> /F                # macOS/Linux: kill <pid>
```

or start on another port (`--port 8001`) and update
`VITE_API_BASE_URL`.

**My `.env` changes have no effect** → (1) you launched from the wrong
folder (must be `backend/`); (2) a real environment variable overrides
`.env` (`echo $env:DATABASE_URL`); (3) you did not restart the server;
(4) the file is named `.env.txt` — Windows Explorer hides extensions, so
create it from the terminal with `copy`.

**`--reload` keeps restarting in a loop, or is very slow** → the file
watcher sees changes inside `.venv` or `__pycache__`. Keep the venv
folder inside `backend/` but restrict watching:
`uvicorn app.main:app --reload --reload-dir app`.

**First request is slow** → the first call per satellite makes two
requests to CelesTrak (metadata, then TLE lines) and imports astronomy
libraries; later calls are cached.

### 10.3 Database, Docker, and Alembic

**`docker: command not found` / `docker compose` unknown command** →
install Docker Desktop. Very old installs use the legacy hyphenated
`docker-compose up -d`.

**`error during connect ... The system cannot find the file specified`**
or **`Cannot connect to the Docker daemon`** → Docker Desktop is not
running. Start it and wait for the "running" state.

**Docker Desktop will not start on Windows** → enable virtualization in
BIOS, install/enable **WSL 2** (`wsl --install` in an admin PowerShell,
then reboot), and make sure Docker Desktop is set to use the WSL 2
backend.

**`port is already allocated` / `bind: Only one usage of each socket
address` on 5432** → a native PostgreSQL is already using 5432. Either
stop it, or change the left side of the port mapping in
`docker-compose.yml` to e.g. `"5433:5432"` and use port `5433` in
`DATABASE_URL`.

**`psycopg.OperationalError: connection failed: Connection refused`** →
the database is not running or wrong host/port. Check
`docker compose ps`; wait for "ready to accept connections" in the logs.

**`password authentication failed for user "postgres"`** → the URL does
not match the container's credentials (`postgres` / `postgres`), or a
different Postgres is answering on that port (see the port conflict
above). If you changed credentials in `docker-compose.yml` *after* the
volume was created, the old password persists in the volume — reset it
with `docker compose down -v` (deletes data).

**`database "satellite_obs" does not exist`** → create it:
`docker compose exec postgres psql -U postgres -c "CREATE DATABASE satellite_obs;"`
(the compose file creates it automatically only on the very first start
of a fresh volume).

**`sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`**
→ wrong URL scheme. It must be `postgresql+psycopg://`.

**`ImportError: no pq wrapper available` (psycopg)** → the binary build
of psycopg is missing. `pip install "psycopg[binary]==3.2.3"`.

**`alembic upgrade head` → `DATABASE_URL is not set`** → set it in
`backend/.env` and run alembic from `backend/`.

**`alembic upgrade head` says nothing to do, but tables are missing /
`relation "..." does not exist`** → the tables were dropped (typically by
running `pytest` against this database) but Alembic's bookkeeping table
`alembic_version` survived, so Alembic thinks it is up to date. Fix:

```powershell
docker compose exec postgres psql -U postgres -d satellite_obs -c "DELETE FROM alembic_version;"
alembic upgrade head
```

Prevent it by only running `pytest` against `satellite_obs_test`.

**`Can't locate revision identified by '...'`** → the database was
stamped by a different version of the migrations. On a dev database:
`docker compose down -v`, `docker compose up -d`, `alembic upgrade head`.

**`503 ... This feature requires a database`** → `DATABASE_URL` is empty
in the environment of the *running server*. Set it, restart uvicorn.

**Tests are skipped ("PostgreSQL not available for database tests")** →
`DATABASE_URL` is not set in that shell, or the database is not reachable.
Set it as shown in section 8.1 and re-run with `pytest -rs`.

**`pytest` wiped my dev data** → you ran it against the dev database. Use
a separate `satellite_obs_test` database; re-apply the fix above and
reload data.

### 10.4 CelesTrak / orbital data

Each satellite fetch now makes **two** requests to CelesTrak - one for the
JSON metadata, one for the raw TLE line text (see the note below on why).
You'll see two `Fetching ... from CelesTrak` log lines per satellite in
the backend terminal; that's normal, not a duplicate request or a retry
loop.

**`502 CelesTrak returned HTTP 403 for NORAD ID ...`** → CelesTrak
refused the request. Causes: too many recent requests from your IP
(CelesTrak rate-limits and temporarily blocks repeated fetches of the same
data), a corporate/school firewall or proxy, or a VPN. The data only
changes a few times a day, so wait a while, avoid `?refresh=true`, keep the
6-hour cache, and try another network if needed. The backend deliberately
returns this as a clean 502 rather than crashing.

**`502` with a timeout / connection error (`The read operation timed
out`)** → no internet, DNS trouble, CelesTrak is slow/down, or a
firewall/proxy is silently dropping the request. Open
`https://celestrak.org` in a browser to check connectivity. The client's
timeout is 10 seconds per request (so up to ~20s worst case for one
satellite, across the two requests); this is more likely on a slow or
restricted network (e.g. some corporate/school Wi-Fi, or certain VPNs). If
Docker is running but the *backend process itself* is not inside a
container, this has nothing to do with Docker - Docker only runs the
database here (see [section 1](#1-what-you-are-running)); the backend's
outbound internet access is whatever your own machine has.

**`422 ... CelesTrak record is missing fields: ['TLE_LINE1', 'TLE_LINE2']`**
→ this was a real bug in an earlier version of this project: CelesTrak's
JSON GP format (`FORMAT=JSON`) only ever returns the OMM keyword fields
(`MEAN_MOTION`, `ECCENTRICITY`, `INCLINATION`, ...) - it does not, and
never did, include the raw TLE line text some code assumed it would. The
fix fetches the TLE lines from a second request (`FORMAT=2LE`) instead of
expecting them in the JSON. If you see this exact error, you're running a
version of the code from before that fix.

**`... CelesTrak TLE response for NORAD ID ... had 3 non-blank line(s),
expected 2`** (or, on the current version, `... did not contain both TLE
lines`) → a second, related bug: CelesTrak documents `FORMAT=TLE` (and
`FORMAT=3LE`) as returning *three* lines - a satellite-name line plus the
two real data lines - not two. `FORMAT=2LE` is the one that returns just
the two data lines with no name line, which is what's actually wanted
here (the name already comes from the JSON request). If you see this
exact error, you're running a version of the code that requested
`FORMAT=TLE` instead of `FORMAT=2LE` - check that
`backend/app/data/celestrak.py`'s `_fetch_tle_lines` method requests
`FORMAT=2LE`, not `FORMAT=TLE`.

If you hit either of the two errors above, make sure you're on the
current version of `backend/app/data/celestrak.py` - its module docstring
explains the two-request split and both quirks; if it doesn't mention
`2LE` at all, it's an old version.

**`422 ...` about orbital data, other than the two messages above** →
CelesTrak returned a record that failed validation (bad TLE checksum,
mismatched IDs, physically implausible values, etc.) or the TLE response
didn't contain a recognizable line 1 / line 2 pair. Retry later - this
usually clears up on the next fetch.

**`404 ... not found` for a NORAD ID** → the ID does not exist or has no
current data (e.g. decayed objects). Verify the ID at celestrak.org.

**Old data / stale predictions** → orbital elements go stale. Check the
`epoch` and `retrieved_at` fields on the satellite record. Force a
refresh with `?refresh=true` (sparingly) or wait for the TTL.

**`GET /api/satellites` returns `[]`** → normal until you have fetched at
least one satellite by NORAD ID, and always empty without a database
(section 4.1).

**Predicted pass times are off by hours** → all API times are **UTC**
(`...Z`). The UI shows them in your browser's local time; compare like
with like.

### 10.5 Tests

**`ArgumentError: Could not resolve all types within mapped annotation`
during collection** → the Python 3.8 issue in 10.1; use the current code.

**Database tests error with `relation ... does not exist` or
`DuplicateTable`** → another process is using the same test database, or a
previous run was interrupted. Re-run; if needed:
`docker compose exec postgres psql -U postgres -c "DROP DATABASE satellite_obs_test;"`
then `CREATE DATABASE satellite_obs_test;`.

**`test_python_compat.py` fails** → someone added Python 3.9+/3.10+
syntax to `app/` or `alembic/`; the message gives file and line. Apply the
replacement it suggests (section 9).

**Coverage errors like `unrecognized arguments: --cov`** → `pytest-cov`
is not installed in your active environment; `pip install -r requirements.txt`.

**Frontend tests fail after a fresh clone** → run `npm ci` (not just
`npm install`) and use Node 18+.

### 10.6 Frontend

**Header says "Backend status: Offline" / "Could not reach the backend.
Is it running?"** → check, in order:
1. Is the backend running? Open `http://localhost:8000/health`.
2. Does `frontend/.env.local` have the right `VITE_API_BASE_URL`? Did you
   restart `npm run dev` after editing it?
3. CORS — open the browser dev tools (F12) → Console. A message like
   *"blocked by CORS policy"* means the page's origin is not in
   `CORS_ORIGINS`. Add it, e.g.
   `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`, and
   restart the backend.
4. Ad blockers/VPNs occasionally block `localhost` calls; try a private
   window.

**`npm install` fails with `ERESOLVE`** → use `npm ci` (respects the
lockfile). Ensure Node is 18+ (`node --version`).

**`npm ERR! engine` / syntax errors from tools at startup** → Node is
too old. Install Node 20 or 22 LTS.

**`EACCES` / `EPERM` errors on install** → close editors and antivirus
scanning the folder, delete `node_modules`, retry; on macOS/Linux avoid
`sudo npm`.

**Vite: `Port 5173 is already in use`** → another dev server is running;
close it (or Vite will pick 5174 — then add that origin to
`CORS_ORIGINS`).

**Blank page after editing `.env.local`** → restart `npm run dev`; hard
refresh (Ctrl+Shift+R).

**Build fails with TypeScript errors** → run `npm run build` and read the
first error; `npm run lint` shows style problems separately.

**`format:check` fails on files you did not touch (Windows)** → usually
line endings after Git converted them to CRLF. Run
`npm run format` to normalize, or set
`git config core.autocrlf input` and re-checkout.

**3D View tab is blank or errors** → the 3D globe needs WebGL. Enable
hardware acceleration in your browser, update graphics drivers, or try
another browser (`chrome://gpu` shows WebGL status). The Sky Path and
Elevation Graph tabs do not need it.

**"Loading 3D view..." stays forever** → the lazily-loaded chunk failed
to load; check the Network tab, hard refresh.

**"No opportunities found"** → not an error; see the note at the end of
[section 7](#7-using-the-app-end-to-end).

**Chunk-size warning during build** → expected and harmless.

### 10.7 Still stuck?

1. Confirm versions: `python --version`, `pip --version`, `node --version`,
   `docker --version`.
2. Confirm your folder: backend commands in `backend/` with `(.venv)`
   active; frontend commands in `frontend/`.
3. Read the **first** error in the output, not the last — later errors are
   often consequences.
4. Run the server with `LOG_LEVEL=DEBUG` in `backend/.env`.
5. Re-run the relevant check from [section 8](#8-testing-everything) to
   isolate whether the problem is code, data, or environment.

---

## 11. Reset / clean-slate recipes

| Goal | Steps |
|---|---|
| Wipe database data only | `docker compose down -v` → `docker compose up -d` → `alembic upgrade head` → recreate `satellite_obs_test` (section 4.3 step 5) |
| Rebuild the Python environment | Delete `backend/.venv`, then repeat section 5.1–5.2 |
| Reinstall frontend packages | Delete `frontend/node_modules`, then `npm ci` |
| Force fresh orbital data | Request `/api/satellites/<id>?refresh=true` (sparingly), or wipe the database |
| Stop everything | Ctrl+C in the backend and frontend terminals; `docker compose stop` |

PowerShell deletes: `Remove-Item -Recurse -Force .venv` and
`Remove-Item -Recurse -Force node_modules`
(macOS/Linux: `rm -rf .venv node_modules`).

---

## 12. Command cheat sheet

```powershell
# --- Database (project root) ---
docker compose up -d                      # start Postgres
docker compose ps                         # status
docker compose stop                       # stop, keep data
docker compose down -v                    # stop and DELETE data
docker compose exec postgres psql -U postgres -d satellite_obs

# --- Backend (backend/, venv active) ---
.\.venv\Scripts\Activate.ps1              # activate venv
pip install -r requirements.txt           # install
alembic upgrade head                      # create/upgrade tables
uvicorn app.main:app --reload             # run API  -> http://localhost:8000/docs
pytest --no-cov                           # tests (set DATABASE_URL to *_test db for all)
ruff check . ; black --check . ; mypy app # quality checks

# --- Frontend (frontend/) ---
npm install                               # install
npm run dev                               # run UI   -> http://localhost:5173
npm test ; npm run lint ; npm run format:check ; npm run build
```

| URL | What |
|---|---|
| http://localhost:5173 | The web app |
| http://localhost:8000/health | Backend health check |
| http://localhost:8000/docs | Interactive API docs (Swagger) |
| http://localhost:8000/redoc | Alternative API docs |
