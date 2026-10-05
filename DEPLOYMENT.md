# Deployment Guide

Target architecture (project plan section 3):

```
GitHub  --push-->  Cloudflare Pages (frontend, static build)
        --push-->  Render (backend, FastAPI + Alembic migrations)
                        |
                        v
                   Neon (PostgreSQL)
```

All three have a free tier this project is designed to fit inside (see
"Costs and free-tier limits" at the end). Nothing here requires a credit
card, but Render and Neon may ask for one to deter abuse - check their
current sign-up flow.

**Order matters**, because the frontend needs the backend's URL, and the
backend's CORS setting needs the frontend's URL:

1. Push the repo to GitHub
2. Create the Neon database
3. Deploy the backend to Render (get its URL)
4. Deploy the frontend to Cloudflare Pages, pointed at that Render URL
   (get *its* URL)
5. Go back and add the Cloudflare Pages URL to the backend's CORS setting

Steps 1-4 below assume a fresh setup; Step 5 closes the loop.

---

## Step 0: Push to GitHub

If the code isn't already in a GitHub repository:

```bash
cd satellite-obs-system
git init
git add .
git commit -m "Initial commit"
```

Create an empty repository on GitHub (no README/license - you already
have those), then:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

Both Render and Cloudflare Pages connect directly to a GitHub repo and
redeploy automatically on every push to `main` - that's the whole
integration; no webhooks to configure by hand.

---

## Step 1: Neon (PostgreSQL)

1. Go to [neon.tech](https://neon.tech) and sign up (GitHub sign-in is
   the fastest path).
2. **Create a project.** Pick a region close to where Render will run
   the backend (Step 2) - cross-region database calls add real latency
   to every request.
3. Neon creates a default database and role for you. Open the project's
   **Dashboard -> Connection Details** (or **Connect** button).
4. Copy the connection string. It looks like:

   ```
   postgresql://neondb_owner:AbC123xyz@ep-cool-name-12345.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

5. **Change the scheme** from `postgresql://` to `postgresql+psycopg://`
   - this project uses the psycopg 3 driver, not the default psycopg2 the
   plain `postgresql://` scheme implies. Keep everything else, including
   `?sslmode=require` - Neon requires SSL and this project's engine setup
   doesn't need to (and shouldn't) turn that off. The result:

   ```
   postgresql+psycopg://neondb_owner:AbC123xyz@ep-cool-name-12345.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

6. Save this string somewhere for Step 2 - it's the `DATABASE_URL` value
   the backend needs. Treat it as a secret (it contains a password);
   never commit it.

**Which connection string, pooled or direct?** Neon's dashboard offers
both a "pooled" connection (through PgBouncer) and a "direct" one. Use
the **direct** connection string here. This backend already manages its
own connection pool (SQLAlchemy, `pool_pre_ping=True` - see
`app/db/session.py`), and layering Neon's pooler underneath a
long-running backend process with its own pool is more likely to cause
odd connection issues than solve anything at this project's scale. Neon's
pooled endpoint is more useful for genuinely serverless/short-lived
callers, which this backend isn't.

**Free tier note:** Neon's free tier autosuspends the compute after a
period of inactivity. The first query after a suspension is slow (a
"cold start" on the database side, separate from Render's own cold
start below) while it wakes back up; `pool_pre_ping=True` means the app
detects and reconnects cleanly rather than erroring - but the first
request after idle time will still be slower than usual. This is
expected, not a bug.

---

## Step 2: Render (backend)

### Option A: Blueprint (recommended - uses `render.yaml`)

This repo includes `render.yaml` at its root, which Render can read
directly.

1. Go to [render.com](https://render.com) and sign up.
2. **Dashboard -> New -> Blueprint.**
3. Connect your GitHub account if you haven't, and select this repo.
4. Render reads `render.yaml` and shows you the service it's about to
   create (`satellite-obs-api`). Click through to create it.
5. Render will prompt for the environment variables marked
   `sync: false` in `render.yaml`:
   - `DATABASE_URL` - paste the Neon connection string from Step 1.
   - `CORS_ORIGINS` - for now, enter `http://localhost:5173` as a
     placeholder (you'll update this in Step 5 once the frontend has a
     real URL). Don't leave this blank - an empty CORS origin list means
     no browser can call the API at all.
6. Click **Apply** / **Create**. Render will build and deploy.

### Option B: Manual dashboard setup (no Blueprint)

If you'd rather configure it by hand (or Blueprints aren't available on
your plan):

1. **Dashboard -> New -> Web Service -> connect this repo.**
2. **Root Directory:** `backend`
3. **Runtime:** Python 3
4. **Build Command:** `pip install -r requirements.txt`
5. **Start Command:**
   ```
   alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
6. **Plan:** Free
7. Under **Environment**, add:
   | Key | Value |
   |---|---|
   | `ENVIRONMENT` | `production` |
   | `LOG_LEVEL` | `INFO` |
   | `PYTHON_VERSION` | `3.11.9` (pins the interpreter; the backend supports 3.8-3.12) |
   | `DATABASE_URL` | the Neon connection string from Step 1 |
   | `CORS_ORIGINS` | `http://localhost:5173` (placeholder for now) |
8. Under **Settings -> Health Check Path**, set `/health`. Render uses
   this to know the service is actually up, not just that the process
   started - relevant on the free tier where the service sleeps and
   Render needs to know when it's really ready again.
9. Click **Create Web Service**.

### Either way: watch the first deploy

Open the service's **Logs** tab. You should see:

```
==> Running 'alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT'
INFO  [alembic.runtime.migration] Running upgrade  -> ..., initial schema
INFO  [alembic.runtime.migration] Running upgrade ... (all migrations)
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:10000
```

If `alembic upgrade head` fails here, the most likely cause is
`DATABASE_URL` being wrong or missing `?sslmode=require` - double check
Step 1.

Render gives the service a URL like:

```
https://satellite-obs-api.onrender.com
```

**Verify it:**

```bash
curl https://satellite-obs-api.onrender.com/health
# {"status":"ok","service":"satellite-observation-api","timestamp":"..."}
```

If this works, the backend and database are live. Keep this URL - the
frontend needs it next.

**Free tier note:** a free Render web service spins down after 15
minutes with no traffic, and the next request wakes it back up (a cold
start of maybe 30-60 seconds). This is normal, documented Render free-tier
behavior, not a problem with this project - the first request after a
quiet period will just be slow once.

---

## Step 3: Cloudflare Pages (frontend)

1. Go to [pages.cloudflare.com](https://pages.cloudflare.com) (or
   **Workers & Pages** in the main Cloudflare dashboard) and sign up/in.
2. **Create a project -> Connect to Git**, select this repo.
3. Configure the build:
   | Setting | Value |
   |---|---|
   | Framework preset | Vite (or leave as "None" and set the fields below manually) |
   | Root directory | `frontend` |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
4. **Environment variables** (still in the same setup screen, or under
   **Settings -> Environment variables** afterward): add
   `VITE_API_BASE_URL` = the Render URL from Step 2
   (`https://satellite-obs-api.onrender.com`, no trailing slash).

   **This is the step most likely to bite you if done out of order:**
   Vite reads `VITE_`-prefixed variables at *build time* and bakes the
   value directly into the compiled JS - not at runtime. If you add or
   change this variable after the first build, it does nothing until you
   trigger a new deploy (**Deployments -> ... -> Retry deployment**, or
   just push a commit).
5. Click **Save and Deploy**.

Cloudflare Pages gives the project a URL like:

```
https://satellite-obs-system.pages.dev
```

**Verify it:** open that URL in a browser. You should see the app shell
and "Backend status: Checking..." briefly. It will very likely then show
**Offline** - that's expected and fixed in the next step: the backend is
up, but doesn't yet know to trust requests from this origin (CORS).

No `_redirects` file or SPA fallback routing config is needed here - this
app has exactly one HTML page and switches views with React state, not
URL-based routing, so there's nothing for Cloudflare Pages to redirect.

---

## Step 4: Close the loop - update CORS on the backend

Now that the frontend has a real URL:

1. Back in **Render -> satellite-obs-api -> Environment**, edit
   `CORS_ORIGINS` to the exact Cloudflare Pages URL from Step 3:

   ```
   https://satellite-obs-system.pages.dev
   ```

   If you also set up a custom domain for the frontend, include both,
   comma-separated, no spaces:

   ```
   https://satellite-obs-system.pages.dev,https://your-custom-domain.com
   ```

2. Save. Render automatically redeploys the service with the new
   environment variable (no code change, no git push needed for this
   one - it's an env var update, not a Blueprint change).
3. Reload the frontend URL from Step 3. **"Backend status: Online"**
   should now appear.

---

## Verification checklist

- [ ] `curl https://<your-render-url>/health` returns `{"status":"ok",...}`
- [ ] `https://<your-render-url>/docs` renders the interactive API docs
- [ ] The frontend shows "Backend status: Online"
- [ ] Creating an observer on the live site (Dashboard -> Save this
      location) succeeds - confirms the database connection, not just
      that the backend process is up
- [ ] Adding a satellite (e.g. NORAD ID `25544`) and clicking "Find best
      opportunities" returns results - confirms the live CelesTrak fetch
      works from Render's network (this sandbox's development network is
      restricted and could never fully verify this end-to-end - your
      deployed backend has normal internet access and should)
- [ ] Opening a pass's details shows the sky path, 3D globe, and
      elevation graph without console errors

---

## Updating a live deployment

Both Render and Cloudflare Pages auto-deploy on push to `main` by
default - normal development is just:

```bash
git add .
git commit -m "..."
git push
```

**Database migrations:** since `alembic upgrade head` runs in the
`startCommand` on every boot (see `render.yaml`), a new migration you add
to `backend/alembic/versions/` is applied automatically the next time
Render redeploys - no manual step needed, and it's a no-op if there's
nothing new to apply.

**Frontend env var changes:** as noted in Step 3, changing
`VITE_API_BASE_URL` (or adding any other `VITE_` variable later) requires
a new Cloudflare Pages deploy to take effect, not just a config save.

---

## Troubleshooting

**Frontend shows "Offline" and the browser console shows a CORS error.**
`CORS_ORIGINS` on Render doesn't exactly match the frontend's origin.
Check for a trailing slash mismatch (the origin has none) and that
you're using `https://`, not `http://`, for the deployed frontend.

**Render deploy fails during `alembic upgrade head`.**
Almost always `DATABASE_URL` - check the scheme is `postgresql+psycopg://`
(not `postgresql://` or `postgres://`) and that `?sslmode=require` is
still on the end of the string from Neon.

**A request to `/api/satellites/{id}` returns 502.**
That's this project's own mapped error for "CelesTrak could not be
reached" (see `app/api/error_handlers.py`) - working as intended if
CelesTrak itself is briefly down or rate-limiting, not a deployment bug.
Retry after a moment.

**First request after a while is very slow, then fine.**
Expected free-tier cold start (Render's service, and/or Neon's compute)
- see the free-tier notes in Steps 1 and 2.

**"relation does not exist" errors after a deploy.**
The migration didn't run. Check the Render deploy logs for the
`alembic upgrade head` output specifically; if it's missing entirely,
confirm `startCommand` in the dashboard matches `render.yaml` (a service
created before a `render.yaml` change won't retroactively pick up the
new command until you sync/redeploy it).

---

## Costs and free-tier limits (as of this writing - check current terms)

| Service | Free tier gives you | Real constraint to know about |
|---|---|---|
| Neon | 1 project, small storage/compute allowance | Compute autosuspends when idle; first query after that is slow |
| Render | 1 free web service | Spins down after 15 min idle; ~30-60s cold start on next request |
| Cloudflare Pages | Effectively unlimited static hosting/bandwidth | 500 builds/month on the free plan - plenty for normal development |

Nothing about this project's architecture assumes more than this (project
plan section 29) - it's designed to run at $0/month, with the explicit
trade-off of occasional cold-start latency rather than an always-warm
paid instance.

## Security checklist before going live

- [ ] `DATABASE_URL` is set only in Render's environment variables, never
      committed (`backend/.gitignore` already excludes `.env`)
- [ ] `CORS_ORIGINS` lists specific origins, not `*`
- [ ] No `.env` file was accidentally committed - `git log --all --
      backend/.env` should show nothing
- [ ] The Neon connection string's password isn't reused anywhere else
