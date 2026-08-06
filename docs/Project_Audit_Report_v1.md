# CakeCraft Studio — Project Audit Report v1

**Date:** 2026-08-05
**Prepared during:** Architecture Freeze
**Scope:** Full codebase audit — no code changes made. This document is read-only analysis.
**Repository state audited:** branch `main`, commit `b5113ea` ("Simplify CORS configuration"), working tree clean, 21 commits total.

---

## 1. Project Overview

CakeCraft Studio ("Maison de Gâteau Paris" in customer-facing copy) is a custom cake ordering platform: customers browse curated cake collections, pick a template, customize it (size/flavor/filling/frosting), review the order, submit contact details, and receive an order confirmation. There is no payment processing, no login/account system, and no bakery-staff/admin interface — the system is customer-facing order intake only.

### Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python), plain functions/services — no ORM |
| Database | Supabase (managed PostgreSQL), accessed via `supabase-py` service-role client |
| Frontend | Static HTML + vanilla JavaScript (no framework, no bundler, no npm build step for the app code) + hand-written CSS |
| Hosting | Railway — **two independent services**: backend (FastAPI/Nixpacks) and frontend (static files served by the `serve` npm package) |
| Migrations | Supabase CLI (`supabase/migrations/*.sql`), 10 migrations applied in sequence |

### Folder Structure

```
cakecraft-studio/
├── backend/
│   ├── app/
│   │   ├── api/routes/        # FastAPI routers (5 files)
│   │   ├── core/              # config.py, database.py
│   │   ├── models/            # empty — no ORM models exist
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   └── services/          # business logic, one file per domain
│   ├── requirements.txt
│   ├── .env / .env.example / app/.env  (see §8 — duplicate .env)
├── frontend/
│   ├── *.html                 # 6 pages, one per step of the funnel
│   ├── js/                    # 10 modules, plain <script defer>, no bundler
│   ├── css/styles.css         # single stylesheet, 1203 lines
│   ├── assets/images/         # served images (referenced by DB rows + code)
│   ├── images/                # separate, partly-unreferenced image folder (see §8)
│   ├── src/data/templates.ts  # orphaned TypeScript file (see §8)
│   ├── serve.json, railway.json, package.json
├── supabase/
│   ├── migrations/            # 10 SQL migration files
│   └── config.toml            # local Supabase CLI config (dev-only)
├── docs/                      # 7 markdown documents (see §7)
├── scripts/                   # empty directory
├── railway.json               # backend Railway service config (repo root)
└── README.md
```

### Architecture Pattern

Backend follows a strict layered flow: **Route → Service → Supabase client**, with Pydantic schemas at the API boundary only. Frontend follows a parallel discipline: each page has one orchestrator JS file that calls shared pure-function utility modules (`pricing.js`, `summary.js`, `validation.js`) and a shared `api.js` for all network calls — no business logic is duplicated between pages. Both layers are documented in `docs/ARCHITECTURE.md` as intentional principles ("Architecture Before Features", "Separation of Concerns") and both are followed consistently in the actual code.

---

## 2. Backend

### Routes (`backend/app/api/routes/`)

| Method & Path | File | Purpose | Error handling |
|---|---|---|---|
| `GET /health` | `health.py` | Liveness check, used as Railway health-check path | none needed |
| `GET /collections` | `collections.py` | List active collections | generic `except Exception` → 500 |
| `GET /templates?collection=` | `templates.py` | List active templates, optional collection filter | generic → 500 |
| `GET /templates/{template_id}` | `templates.py` | Single template by UUID | 404 if not found, generic → 500 |
| `GET /designer/options` | `designer.py` | All four option groups (sizes/flavors/fillings/frostings) | generic → 500 |
| `GET /designer/{template_id}` | `designer.py` | Template + all options combined (Designer page init) | 404 if template missing |
| `POST /orders` | `orders.py` | Create an order | `ValueError` → 400 (bad option id), `None` → 404 (bad template id), generic → 500 |
| `GET /` | `main.py` | Root welcome message | — |

All routes are unauthenticated and world-readable/writable — there is no auth layer anywhere in the API (see §6/§9).

### Services (`backend/app/services/`)

- **`collection_service.py`** — `get_active_collections()`: `collections` table, filters `active=true`, orders by `display_order`.
- **`template_service.py`** — `get_active_templates(collection)`: filters `active=true`, optional case-insensitive `category` match; `get_template_by_id(id)`: `.maybe_single()` lookup.
- **`designer_service.py`** — shared `_get_active_options(table)` helper reused across `cake_sizes`/`flavors`/`fillings`/`frostings`; `get_designer_initialization(template_id)` returns `None` if the template doesn't exist, else `{template, options}`.
- **`order_service.py`** — the only service with real business logic:
  - Re-validates every submitted option id server-side against the live options table (`_find_option`) — a client cannot submit an id that doesn't exist or belongs to a different category.
  - Computes `total_price = template.base_price + cake_size.price_adjustment`. **Flavor, filling, and frosting never affect price** — this is a deliberate simplification, consistently mirrored in the frontend's `pricing.js` (same formula), not a bug, but see §9.
  - `_find_or_create_customer()` dedupes by exact `email` match (no DB unique constraint backs this — see §4).
  - Stores the full selected option objects (not just ids) into `orders.configuration` (JSONB) as a point-in-time snapshot.

### Schemas (`backend/app/schemas/`)

- `CollectionResponse`, `CakeTemplateResponse`, `DesignerOptionResponse`/`CakeSizeResponse`/`DesignerOptionsResponse`/`DesignerInitResponse` — all straightforward Pydantic response models matching their DB rows.
- `OrderCreateRequest` — the only *request* schema in the system: `template_id`, `cake_size_id`, `flavor_id`, `filling_id`, `frosting_id` (all plain `str`, not `UUID`, inconsistent with the `uuid.UUID` path-param typing used in `templates.py`/`designer.py`), `customer_name: str`, `customer_phone: str`, `customer_email: str` (plain `str`, not Pydantic's `EmailStr` — no format validation at the schema level; email format is only checked client-side via HTML5 `type="email"`), `notes: str | None`.

### Core (`backend/app/core/`)

- **`config.py`** — loads `backend/.env` explicitly by resolved path; `Settings` is a plain class (not `pydantic.BaseSettings`) exposing `app_name`, `version`, `supabase_url`, `supabase_key`. `supabase_url`/`supabase_key` read via `os.environ[...]` — will raise `KeyError` at import time (hard startup failure) if unset, rather than a validation error.
- **`database.py`** — single module-level `supabase: Client` instance, imported wherever DB access is needed. No connection pooling/retry logic (not needed at Supabase-client scale).

### Models

`backend/app/models/__init__.py` is empty. There is **no ORM** anywhere in the codebase — all data access is raw dict-based Supabase client calls (`.table(...).select(...).eq(...).execute()`), and Pydantic schemas exist only at the API request/response boundary, not as a data-access layer.

### Authentication

**None exists.** No login, no signup, no session/cookie/JWT handling, no user table with credentials. `PyJWT` appears in `requirements.txt` only as a transitive dependency of another package — grep across the entire backend confirms zero JWT/auth code. Every table has RLS *enabled* in Postgres, but the backend connects with the Supabase service-role key, which bypasses RLS entirely; the original migration comment states this is intentional pending "real policies... once end-user auth is introduced" — that step has not happened.

### AI Modules

**None exist in the backend.** See §6.

---

## 3. Frontend

### Pages (all in `frontend/`, one per funnel step)

| Page | Purpose | Scripts loaded |
|---|---|---|
| `index.html` | Landing page: hero, collections grid (loaded from API), "Why Us", "How It Works", footer | `api.js`, `collections.js`, `app.js` |
| `templates.html` | Template gallery for a collection (collection read from `?collection=` query param) | `api.js`, `app.js`, `templates.js` |
| `designer.html` | Cake customization: options, live price, live summary, live validation | `api.js`, `app.js`, `pricing.js`, `summary.js`, `validation.js`, `designer.js` |
| `order-review.html` | Read-only recap of the configured cake before checkout | `api.js`, `app.js`, `pricing.js`, `summary.js`, `validation.js`, `order-review.js` |
| `customer-information.html` | Contact-details form + order submission | `api.js`, `app.js`, `customer-information.js` |
| `confirmation.html` | Thank-you page showing the returned order id | `app.js`, `confirmation.js` |

### JS Modules (`frontend/js/`)

**Shared infrastructure:**
- `api.js` — the only file that calls `fetch()`. Four functions: `getCollections`, `getTemplates`, `getDesignerInit`, `createOrder`. `API_BASE_URL` is hardcoded to the production Railway backend URL (see §5/§8 — the comment above it is stale and describes different, dynamic-hostname behavior that is no longer implemented).
- `app.js` — cross-page concerns only: mobile nav toggle, footer year, and (on `index.html` specifically) `loadCollections()`.
- `pricing.js` — pure function `calculateCurrentPrice(designerState)` + `getServingRange(designerState)`. No DOM, no fetch.
- `summary.js` — pure function `buildOrderSummary(designerState)`. No DOM, no fetch.
- `validation.js` — pure function `validateOrder(designerState)`, checks all 5 required fields (template, cakeSize, flavor, filling, frosting) are present.

**Page orchestrators:** `collections.js`, `templates.js`, `designer.js`, `order-review.js`, `customer-information.js`, `confirmation.js` — each owns DOM rendering and event wiring for exactly one page, and each reuses the shared pure-function modules rather than reimplementing pricing/summary/validation logic. This convention is followed with no exceptions found.

### User Flow (happy path)

1. **Landing (`index.html`)** → collections fetched from `GET /collections`, rendered as clickable cards.
2. Click a collection → **`templates.html?collection=X`** → `GET /templates?collection=X`, rendered as cards with "Design This Cake" buttons.
3. Click a template → **`designer.html?id=<templateId>`** → `GET /designer/{id}` returns template + all 4 option groups; user picks one radio per group; price/summary/validation update live via the three pure-function modules; "Continue" is disabled until all 4 groups are chosen.
4. Continue → **`order-review.html?id=&cakeSize=&flavor=&filling=&frosting=`** (state carried entirely via URL query params — no client-side storage/session at all) → re-fetches `GET /designer/{id}` and reconstructs the same `designerState` shape client-side to redisplay price/summary via the same pure functions (no duplicated logic, but each page reload re-fetches full designer data from the network rather than reusing what was already fetched in the Designer step).
5. Continue → **`customer-information.html`** (same query string forwarded) → HTML5-native form validation (`required`, `type="email"`, `type="tel"`) gates the Submit button; on submit, `POST /orders` is called with the 5 option ids + 4 customer fields.
6. On success → **`confirmation.html?orderId=<id>`** → displays the returned order id. On failure, an inline error message is shown and the Submit button re-enables (no retry/backoff logic — a manual re-click is required).

### Forms

Exactly one form exists in the whole app: `customerInfoForm` on `customer-information.html` (name, phone, email, optional notes). Validation is entirely native HTML5 (`required`/`type` attributes read via `form.checkValidity()`); there is no custom validation logic, no client-side phone-format checking, and — as noted in §2 — no server-side email-format validation either (the backend schema types `customer_email` as plain `str`).

### API Integrations

The frontend talks to exactly four backend endpoints (`GET /collections`, `GET /templates`, `GET /designer/{id}`, `POST /orders`) via the four functions in `api.js`. There is no other network integration (no analytics, no error-tracking SDK, no payment SDK, no email service, no maps/geocoding, no third-party AI SDK).

### Design System

`frontend/css/styles.css` (1203 lines, single file, no preprocessor) implements a token system in `:root` (ivory/gold/brown/rose-gold palette, Playfair Display + Inter fonts, an `--space-1`…`--space-6` spacing scale) and a page-scoping convention (`#designer`, `#order-review`, `#customer-info`, `#confirmation`, `#templatesGrid` prefix selectors) so shared classes like `.collection-card`, `.section-title`, and `.btn-primary` render consistently without leaking page-specific overrides into each other. Mobile-first breakpoints exist at 640/720/860/1024px.

---

## 4. Database

Database is Supabase-hosted PostgreSQL, schema-managed entirely through 10 sequential Supabase CLI migrations (no manual/undocumented schema drift found — the migrations fully explain the current schema). RLS is enabled on every table, but every policy is effectively "deny all via the Data API" — the FastAPI backend bypasses it completely via the service-role key, so RLS currently provides no real access control (see §2 Authentication, §9).

### Tables

**`bakery`** — single-bakery model, one seeded row ("Maison de Gâteau Paris"). `id, name, email, phone, address, created_at`.

**`collections`** — the 5 landing-page categories. `id, name, description, image, display_order, active, created_at`. Index on `(active, display_order)`. Seeded idempotently; `image` values were later updated from `.svg` placeholders to real `.png` photos (see below).

**`cake_templates`** — 15 seeded rows, 3 per collection. `id, bakery_id (FK→bakery, cascade), name, category (text), style, base_price (numeric, check ≥0), preview_image, active, created_at`. Index on `bakery_id`.
  ⚠️ **`category` is a free-text column, not a foreign key to `collections.id`.** Collection↔template matching happens by case-insensitive string comparison in `template_service.py` (`.ilike("category", collection)`), not a database relationship. There is no referential-integrity guarantee that a template's `category` matches an actual `collections.name` value.

**`customization_options`** — created in the initial schema (`template_id FK, type, value, price_adjustment, display_order, active`) but **never queried anywhere in the current codebase**. It was superseded by the four dedicated tables below and is now dead schema — no service, route, or migration references it after creation.

**`cake_sizes`, `flavors`, `fillings`, `frostings`** — four structurally identical lookup tables (`id, name, display_order, active, created_at`), each with an `(active, display_order)` index, each seeded with 3 realistic values. `cake_sizes` additionally has `price_adjustment (integer, default 0)`, `servings_min`, `servings_max` (added in a later migration; Small/Medium/Large seeded with $0/$50/$100 adjustments and 8–10/12–15/18–22 serving ranges respectively). `flavors`, `fillings`, and `frostings` have **no pricing or serving-count columns at all** — they are purely cosmetic/aesthetic selections with zero effect on price (see §9).

**`customers`** — `id, name, email, phone, created_at`. **No unique constraint on `email`**, even though `order_service.py`'s `_find_or_create_customer()` relies on `email` being effectively unique to dedupe customers — under concurrent requests this could create duplicate customer rows for the same email (low real-world risk at current traffic, but a real schema/application-logic mismatch).

**`orders`** — `id, customer_id (FK→customers, restrict), template_id (FK→cake_templates, restrict), pickup_date (date), pickup_time (time), status (text, check in pending/confirmed/in_progress/ready/completed/cancelled, default 'pending'), total_price (numeric, check ≥0), configuration (jsonb, default {}), notes, created_at`. Indexes on `customer_id`, `template_id`, `pickup_date`, `status`.
  ⚠️ `pickup_date`/`pickup_time` were originally `not null`, then relaxed to nullable by migration `20260801090000_relax_orders_pickup_columns.sql`, whose comment explains no milestone through Order Submission collects a pickup date/time yet, and that the columns should revert to `not null` once pickup scheduling is implemented. **Every order currently created has `pickup_date`/`pickup_time = null`** — pickup scheduling is unimplemented end-to-end (no UI, no API field, no service logic).

### Data-only migrations

Three later migrations contain no schema changes, only `UPDATE` statements repointing `collections.image` and `cake_templates.preview_image` — first from placeholder SVGs to real PNG photography, then from PNG to optimized WebP (960px, ~50–90KB, down from ~2MB PNG originals; JPEG fallback served client-side for browsers without WebP support).

### Missing Entities

No tables exist for: bakery staff/admin users, authentication/credentials, payments/transactions, pickup scheduling, order status history/audit log, reviews/ratings, inventory, or any AI-related data (prompts, generated images, conversation history).

---

## 5. Deployment

### Railway — two independent services

**Backend service** (`railway.json`, repo root):
```json
{
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 100,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```
`requirements.txt` now lives at `backend/requirements.txt` (moved from repo root in a recent commit), implying the Railway service's configured Root Directory is `backend`. Live at `https://web-production-c9dd99.up.railway.app`.

**Frontend service** (`frontend/railway.json`, self-contained inside `frontend/` to avoid colliding with the backend's root-level config when both services share the monorepo):
```json
{
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "serve -l tcp://0.0.0.0:$PORT .",
    "healthcheckPath": "/",
    ...
  }
}
```
Served by the `serve` npm package (`^14.2.4`, only production dependency in `frontend/package.json`). `frontend/serve.json` sets `{"cleanUrls": false}` — required because `serve`'s default clean-URL redirect behavior drops query strings, which would break every internal page navigation in this app (all inter-page state is carried via URL query params, per §3).

### Environment Variables

- Backend requires `SUPABASE_URL`, `SUPABASE_KEY` (read via `os.environ[...]`, hard failure if missing). `.env.example` also documents an **optional** `CORS_ALLOW_ORIGIN_REGEX` — this variable is now dead: current `main.py` no longer reads any CORS-related env var at all (see below), so setting it on Railway would have no effect. `.env.example` was not updated to reflect this.
- No frontend environment variables are used at all — `API_BASE_URL` is a hardcoded string literal in `frontend/js/api.js`, not sourced from any env/config mechanism (there is no build step that could inject one).

### CORS

Current `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
This wide-open configuration allows any web origin to call the API. `allow_credentials=False` means cross-origin requests cannot carry cookies/credentials, which limits the practical impact, but the wildcard origin itself is a production-hardening gap (see §9). This replaces an earlier, narrower `allow_origin_regex` mechanism (env-var driven, restricted to localhost/LAN/production-frontend patterns) that existed previously in this codebase's history but is no longer present.

### Production Readiness Assessment

| Aspect | Status |
|---|---|
| Backend deployed & reachable | ✅ Live on Railway |
| Frontend deployed & reachable | ✅ Live on Railway (standalone service) |
| HTTPS | ✅ (Railway-provided) |
| CORS | ⚠️ Wildcard — see above |
| Secrets management | ✅ `.env` files correctly gitignored; Railway env vars used in production |
| Health checks | ✅ `/health` (backend), `/` (frontend) both wired into Railway's restart policy |
| Automated tests / CI | ❌ None exist (no test files, no `.github/workflows`, no CI config anywhere in the repo) |
| Logging/monitoring/error-tracking | ❌ None beyond Railway's own platform logs; no APM/error-tracking SDK integrated |
| Rate limiting / abuse protection | ❌ None — `POST /orders` is fully open and unauthenticated |
| Frontend/backend coupling | ⚠️ Frontend's `API_BASE_URL` is hardcoded to one specific backend URL; a backend URL change requires a frontend code change + redeploy, not a config change |

---

## 6. AI Features

**None exist in the current codebase.** A full-repository search (`grep -rniE "openai|anthropic|gpt|claude|dall-?e|stable.?diffusion|image.?generat|ai.?model|llm"` across `backend/app` and `frontend/js`) returned zero matches in both. There is:
- No AI/LLM API integration of any kind (no OpenAI/Anthropic/other SDK in `requirements.txt` or `package.json`).
- No image-generation feature (the real cake photography visible on the live site was sourced and placed as static assets during development — it is not generated at request time by any AI service).
- No prompt-based interaction anywhere in the UI.
- No AI-related database tables, columns, or migrations.

`README.md` currently reads: *"AI-Native Cake Designer Platform built with FastAPI, Supabase and Railway."* — this "AI-Native" claim does not correspond to any implemented feature at this time. `docs/ARCHITECTURE.md` is more precise on this point, explicitly framing AI as a **future** enhancement ("AI Is an Enhancement, Not the Foundation... the platform must remain fully functional without AI capabilities"), which matches the current codebase's actual state — the platform is fully functional with zero AI dependency.

---

## 7. Existing Documentation

Seven markdown files exist under `docs/`, in addition to the root `README.md` and `LICENSE`.

| Document | Content | Currency |
|---|---|---|
| `ARCHITECTURE.md` | Vision, 10 guiding principles, system overview, ASCII layered-architecture diagram | **Substantially incomplete** — Sections 5–13 (Frontend Architecture, Backend Architecture, Database Architecture, API Architecture, Designer Engine, Development Workflow, Coding Standards, Release Strategy, Future Vision) exist only as empty headings with no body content. |
| `PROJECT_RULES.md` | Project philosophy, tech stack, dev rules, git commit format, Definition of Done | Current and accurate; matches observed practice (stack, commit conventions). |
| `UI_VISION.md` | Design goals, color palette, typography, imagery, component style | Current and accurate; matches the implemented CSS design-token system and real photography. |
| `RELEASE_0.2.md` | Defines Milestones 9–12 (Order Review → Order Submission → Order Confirmation) | **Stale** — every milestone is still marked "Planned"/"Status: Planning", but all four are fully implemented and working in the current codebase (Order Review, Customer Information, and Confirmation pages all exist and function end-to-end). |
| `MILESTONE_09_SPEC.md` | Order Review page spec | **Stale** — header says "Status: Planning"; the page is fully implemented exactly as specified (image, name, size, flavor, filling, frosting, serving range, price, Return/Continue actions). |
| `MILESTONE_10_SPEC.md` | Customer Information page spec | No explicit status field, but describes work that is fully implemented; matches the shipped page closely (name/phone/email/notes, back/submit actions, validation gating submit). |
| `IMAGE_LIBRARY.md` | Checklist of brand/collection/template images to source | **Stale** — every single row is still marked "⬜" (not done), despite all listed images (and more) now being sourced, optimized, and live in production. |

No specification document exists for the Order Submission (backend `POST /orders` wiring) or Order Confirmation milestones, despite both being fully implemented — the written specs stop at Milestone 10 (Customer Information) while the shipped product goes further (submission + confirmation page both work).

---

## 8. Code Quality Review

### Folder Organization

Backend follows a clean, conventional FastAPI layout (`api/routes`, `core`, `models`, `schemas`, `services`) with one file per domain concept, consistently named. Frontend follows a matching one-file-per-concern convention. Both are easy to navigate and the convention has no exceptions.

### Naming Consistency

Generally consistent (`snake_case` Python, `camelCase` JS, kebab-case file/URL names). One typing inconsistency: `OrderCreateRequest` fields (`template_id`, `cake_size_id`, etc.) are typed as plain `str` while the equivalent path parameters elsewhere (`templates.py`, `designer.py`) are typed `uuid.UUID` — the same conceptual value (a template id) is validated differently depending on whether it arrives as a path param or a request body field.

### Separation of Concerns

Strongly upheld throughout: pure-function modules (`pricing.js`, `summary.js`, `validation.js`, and their backend service-layer equivalents) never touch the DOM or the network; page orchestrators never contain pricing/validation math; `api.js` is the sole fetch boundary on the frontend; routes never talk to Supabase directly, always through a service function. This is the strongest aspect of the codebase.

### Technical Debt / Findings

1. **Stale comment in `frontend/js/api.js`.** The comment above `API_BASE_URL` describes dynamic same-hostname resolution ("Same hostname the page was loaded from... automatically targets the right LAN IP...") but the actual code is a hardcoded production URL string. The comment no longer describes the code beneath it.
2. **Orphaned `customization_options` table** — created in the first migration, never read or written by any current route/service (see §4).
3. **Orphaned `backend/app/.env`** — a second, near-empty `.env` file exists alongside the real `backend/.env`; `config.py` only ever loads the latter, so this file is dead and could confuse a future contributor about where secrets are actually configured.
4. **Orphaned `frontend/src/data/templates.ts`** — a single TypeScript file (with a full `CakeTemplate` interface and 15 hardcoded template objects) in a project with no TypeScript tooling anywhere else (no `tsconfig.json`, no build step that would compile it, no reference to it from any HTML/JS file). Its data has also drifted from the live database (different ids/descriptions/tag fields not present in the real schema, e.g. `shape`, `tiers`, `premium`, `featured`, `difficulty`, `tags`). It is not part of the running application.
5. **Orphaned `frontend/images/collections/*`** — 5 collection hero images (including one with a raw, un-slugified filename: `Chocolate Confetti Celebration(2).png`) that are not referenced by any code or DB row; the live app instead serves collection images from `frontend/assets/images/`. Only `frontend/images/brand/hero-v1.png` (the landing-page hero) is actually used from this second `images/` tree — the rest is unused staging content.
6. **Orphaned `frontend/assets/images/cake-*.svg`** — the five original placeholder illustrations, superseded by `.png`/`.webp` photography per the data migrations in §4, left on disk unreferenced by any current DB row (except `hero-cake.svg`, which several JS files still use as a broken-image fallback).
7. **Leftover debug `console.log` calls** — `collections.js` (`console.log("Clicked:", collection.name)`) and `designer.js` (`console.log(designerState)`) log on every user interaction in production.
8. **Empty `scripts/` directory** at the repo root — no files at all.
9. **Stale `.env.example` documentation** — describes a `CORS_ALLOW_ORIGIN_REGEX` variable that current `main.py` no longer reads (see §5).
10. **No automated tests anywhere** — no `tests/` directory, no `pytest`/`unittest`/JS test files, no CI configuration (`.github/workflows` does not exist). All verification described in `docs/PROJECT_RULES.md` ("Test every feature") appears to have been manual/browser-based rather than automated.
11. **`ARCHITECTURE.md` is roughly half-written** — 8 of its 13 planned sections are empty headings (see §7).

### What's Working Well

- Zero business-logic duplication between frontend and backend price calculation (`pricing.js` and `order_service.py` implement the identical formula independently and stay in sync).
- Consistent, deliberate page-scoping CSS convention prevents cross-page style leakage despite a single shared stylesheet.
- Every service function has a single, obvious responsibility; no god-objects or god-functions found.
- Real, optimized production photography (WebP + JPEG fallback) replacing placeholder art — a genuine polish pass that's fully wired end-to-end (DB → API → frontend `<picture>` elements).

---

## 9. Missing Requirements

Gaps relative to a typical production custom-cake-ordering platform, and relative to the project's own documentation (`RELEASE_0.2.md`, `ARCHITECTURE.md`):

- **No authentication/authorization system** — no customer accounts, no bakery-staff/admin login, no way to view past orders. Every `orders` row is only reachable by whoever holds its UUID (returned once, on the confirmation page).
- **No pickup scheduling** — `orders.pickup_date`/`pickup_time` exist in the schema but are always `null`; no UI step collects them.
- **No payment integration** — orders are created with a `status` of `pending` and no transaction/payment record ever exists.
- **No order-status workflow for staff** — `status` supports 6 values (`pending`→…→`cancelled`) via a DB check constraint, but nothing in the codebase ever transitions an order out of `pending`; there is no staff-facing view or endpoint to do so.
- **No email/SMS notification** — the confirmation page says "We'll contact you shortly," but no email-sending integration exists to make that happen automatically.
- **Flavor/filling/frosting have zero price impact** — only cake size affects `total_price`; a real bakery would typically price premium flavors/fillings/frostings differently.
- **No inventory/capacity constraints** — the system never checks bakery capacity, blackout dates, or lead time before accepting an order.
- **No admin/back-office interface** at all — collections, templates, and options can currently only be edited by writing SQL directly against Supabase.
- **No automated tests or CI pipeline**, despite `PROJECT_RULES.md`'s Definition of Done explicitly requiring "It is tested."
- **No rate limiting / spam protection** on `POST /orders` (or any endpoint) — anyone can submit unlimited fake orders.
- **`customization_options` table and `frontend/src/data/templates.ts`** represent an earlier, abandoned data-modeling approach that was never cleaned up after the current one (four dedicated option tables) replaced it.
- **No documented specs beyond Milestone 10** — Order Submission and Order Confirmation are implemented but were never captured as milestone specs the way Milestones 9–10 were.

---

## 10. Recommendations

These are observations for future planning only — **no action is being taken as part of this audit.**

1. **Tighten CORS before wider production traffic.** Replace `allow_origins=["*"]` with an explicit allow-list (or restore the previous `allow_origin_regex` approach) once the frontend's production origin is finalized and stable.
2. **Reconcile `frontend/js/api.js`'s comment with its code**, or restore the dynamic-hostname behavior the comment describes if local/LAN development against a local backend is still a workflow that's needed.
3. **Decide the fate of dead schema and dead files** — drop or explicitly document `customization_options` as legacy; delete or clearly quarantine `frontend/src/data/templates.ts` and the unused `frontend/images/collections/*` and `frontend/assets/images/cake-*.svg` assets so future contributors don't mistake them for live code/data.
4. **Add a unique constraint on `customers.email`** to match the assumption already baked into `_find_or_create_customer()`.
5. **Type `OrderCreateRequest`'s id fields as `UUID` and `customer_email` as `EmailStr`** for consistency with the rest of the schema layer and to move email-format validation server-side.
6. **Update `docs/RELEASE_0.2.md`, the two milestone specs, and `docs/IMAGE_LIBRARY.md`** to reflect actual shipped status — all currently understate what's been built, which risks a future contributor (or reviewer) redoing already-finished work or misjudging project progress.
7. **Finish or trim `docs/ARCHITECTURE.md`** — either fill in the 8 empty sections or remove the placeholder headings so the document doesn't imply missing content is merely unwritten when some of it (e.g., Coding Standards, Development Workflow) may already be de facto established by convention and just needs transcribing.
8. **Revisit the "AI-Native" claim in `README.md`** — either scope it to future roadmap language (consistent with `ARCHITECTURE.md`'s own framing) or remove it, since no AI capability currently exists.
9. **Add a minimal automated test layer** before further feature work, starting with the highest-value/highest-risk path: `order_service.create_order()`'s option-validation and price-calculation logic, and the pure frontend utility modules (`pricing.js`, `summary.js`, `validation.js`), which are already pure functions and trivially unit-testable.
10. **When authentication is eventually introduced** (already anticipated in the initial-schema migration comment), revisit RLS policies at the same time — currently every table's RLS is enabled but functionally inert because the backend's service-role key bypasses it entirely.
11. **Before scaling traffic, add basic rate limiting to `POST /orders`** and consider what monitoring/alerting is needed given there is currently no error-tracking or APM integration.

---

*End of audit. No source files were modified in the course of this review; this report is the only file added to the repository.*
