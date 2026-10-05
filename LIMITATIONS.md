# Known Limitations

A single consolidated list of this project's known limitations,
organized by category, rather than scattered across individual docs.

## Scientific / data accuracy

- **Illumination uses a simplified cylindrical Earth-shadow model** (no
  penumbra, spherical rather than oblate Earth). Standard simplification
  for this purpose; not a precise eclipse calculation.
- **Brightness is not modeled at all**, beyond the illumination/range/
  darkness factors that feed the heuristic score. The project plan is
  explicit that precise visual-magnitude prediction is out of scope.
- **The Observation Suitability Score is a heuristic, not a probability.**
  The weights and curves in `core/scoring.py` are documented, reasonable
  defaults - not the only reasonable choice, and not physical law.
- **Orbital elements go stale.** A satellite's predicted position drifts
  from reality as its cached TLE ages; the cache TTL (default 6 hours)
  bounds this but does not eliminate it. See Phase 15 (optional) for the
  research question this motivates.
- **Charts and the 3D globe interpolate between three real points**
  (rise/peak/set) rather than showing a continuous ephemeris - the
  backend does not expose one. Documented in `frontend/src/utils/passGeometry.ts`.
- **The 3D globe's Earth is a stylized lat/lon grid**, not real satellite
  imagery or accurate continent shapes - deliberate, to avoid an external
  texture asset or CDN dependency.
- **Daylight is treated as a near-total visibility gate** for all three
  observation methods; specialized daylight satellite tracking (used by
  some professional/amateur setups) isn't modeled.

## Feature scope

- **Satellite discovery is a curated list plus live search, not a full
  catalog browser.** `GET /api/satellites/catalog` returns a short,
  hand-picked list of well-known satellites, and `GET
  /api/satellites/search?q=` searches by name live against CelesTrak.
  There is still no way to browse CelesTrak's full catalog (tens of
  thousands of objects) - ranking and prediction only cover satellites
  the caller explicitly lists (by catalog entry, search result, or
  direct NORAD ID).
- **`object_type`, country, and launch date are never populated** on a
  `Satellite` record - CelesTrak's GP endpoint (used for orbital
  elements) doesn't return them; a separate SATCAT lookup would be
  needed.
- **No pagination** on `GET /api/satellites`, `/api/observers`, or
  `GET /api/passes/search`. Fine at the project's current scale; would
  need adding if any of these lists grew large.
- **No authentication.** Not planned for the MVP (project plan section
  28).
- **`orbital_elements` grows one row per fetch per satellite**, with no
  retention/pruning policy. Cheap at current scale; worth revisiting if
  a satellite is fetched very frequently over a long period.

## Performance

- **Ranking across many satellites is sequential**, not parallelized.
  Roughly 3 seconds per satellite for a 12-hour search window (measured,
  Phase 10) - fine for the default candidate list (one satellite, the
  ISS) and the project's stated scale (a personal portfolio demo, not
  high concurrent production load); a candidate for a follow-up if the
  default candidate list ever grows meaningfully.
- **Pass-search refinement (bisection/peak-search) is not vectorized**,
  unlike the coarse sampling grid (Phase 10). This costs a few hundred
  milliseconds per detected pass - small relative to the coarse search,
  but a known, understood remaining cost if search windows grow much
  larger than a day.

## Testing

- **Database-backed tests require a real, reachable PostgreSQL
  instance** and are skipped (not failed) otherwise - deliberate, so
  SQLite-vs-Postgres differences (constraint enforcement, JSON handling)
  can't hide real bugs, at the cost of needing Postgres available to run
  the full suite. See `README.md`'s "Running locally" section for setup,
  and its warning about not pointing `DATABASE_URL` at data you care
  about while testing (the suite creates/drops tables directly, outside
  Alembic's tracking).
- **Three.js (the 3D globe) is not unit-tested** - jsdom has no WebGL
  context. Its pure coordinate math (`globeMath.ts`, `passGeometry.ts`)
  is tested; the rendering itself is only verified by building
  successfully and manual/visual review.

## Infrastructure

- **Free-tier hosting constraints apply** once deployed: backend
  cold-starts after inactivity (Render free tier), limited database
  compute/storage (Neon free tier), and CelesTrak's own rate limits are
  all real constraints - see `DEPLOYMENT.md`.
