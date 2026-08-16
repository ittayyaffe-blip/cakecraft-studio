# CakeCraft Studio — Final Architecture

**Status: CURRENT / AUTHORITATIVE.** This document describes the system as it is actually implemented and deployed today, verified against the current repository, live production data, and the current automated test suite (582/582 passing — see `docs/TESTING_AND_VALIDATION.md`) — not against earlier plans or superseded roadmap documents. For the project's development history, see the sprint documents listed in `docs/README.md`.

## 1. Project Purpose

CakeCraft Studio ("Maison de Gâteau Paris") is a custom-cake ordering platform built to demonstrate a realistic, end-to-end application of modern software engineering practice: a layered web application, two real external communication integrations (Email via Resend/Gmail, WhatsApp via Twilio Sandbox), an AI/RAG-assisted customer communication layer, an ML demand-forecasting model, and — the project's central engineering contribution — a human-in-the-loop safety architecture where AI can draft customer communication but can never send it unsupervised.

## 2. Academic / Demo Scope

This is a final-degree academic project, not a commercial product. It uses a realistic bakery scenario to demonstrate the architecture; it is not intended to operate as a real business, does not process real payments (see §16, Simulated Payment), and its "customers" are synthetic demo records except where noted (see `docs/TESTING_AND_VALIDATION.md` for what was validated with real, live infrastructure vs. automated tests).

## 3. System Overview

```text
                          Customer
                             │
              ┌──────────────┼───────────────┐
              ▼              ▼                ▼
        Website Journey   Chat Widget    WhatsApp / Email
        (Templates →      (slot-filling  (Twilio Sandbox /
         Designer →        ordering +     Gmail IMAP+Resend)
         Order Review →    Q&A, same
         Customer Info →   widget)
         Simulated
         Payment)
              │              │                │
              └──────────────┼────────────────┘
                             ▼
                ┌─────────────────────────┐
                │      FastAPI Backend     │
                │       Route Layer        │
                └────────────┬─────────────┘
                             │
                             ▼
                ┌─────────────────────────────────────┐
                │             Service Layer             │
                ├──────────┬──────────┬────────────────┤
                │  Orders  │Customers │  Notifications  │
                │ Payment  │  Agent   │  Communication  │
                │  RAG     │ Forecast │    Adapters     │
                └────┬─────┴────┬─────┴────────┬────────┘
                     │          │               │
                     ▼          ▼               ▼
              ┌───────────┐ ┌────────┐  ┌────────────────┐
              │ Supabase  │ │ Claude │  │  Communication  │
              │ Postgres  │ │(Sonnet)│  │    Adapters     │
              │ + Auth    │ └────────┘  │ ┌───────┬──────┐│
              │ + pgvector│             │ │ Resend│Twilio││
              └───────────┘             │ │(email)│ (wa) ││
                                         │ └───────┴──────┘│
                                         └─────────────────┘
```

The AI communication path (WhatsApp/Email inbound → customer reply, and the website live-chat Q&A) is a distinct flow through the same service layer:

```text
Inbound Message (Email or WhatsApp) / Website Chat Question
        │
        ▼
Customer Identification (by email / phone)
        │
        ▼
Order Matching (none / one confident match / ambiguous)
        │
        ▼
Conversation Context (this customer's recent prior messages)
        │
        ▼
Fast path? (an obvious "new order" message skips RAG/Claude entirely
            and gets a deterministic Website-First reply — see §9)
        │  (otherwise)
        ▼
RAG Retrieval (CakeCraft knowledge base)
        │
        ▼
Claude (drafts language, classifies intent, self-reports confidence)
        │
        ▼
Application Guardrails (app-owned risk tier — see AI_RAG_AND_SAFETY.md)
        │
        ▼
Draft Notification (status = draft) — except live Chat Q&A, which shows
        │                              the answer to the customer directly
        │                              and records it, never auto-sending
        │                              a real Email/WhatsApp message
        ▼
Human Review → Send (see COMMUNICATIONS_AND_HUMAN_APPROVAL.md)
```

Chat-assisted **ordering** (as opposed to Q&A) is a separate, narrower AI use: Claude only ever extracts/updates selections against the real catalog and judges whether a message is an explicit confirmation — the application independently validates every id and gates order creation behind three independent checks (Claude's own signal, every required field actually known, and a deterministic keyword check on the raw message). See §15.

## 4. Frontend

Static HTML/CSS/vanilla JavaScript, no build step, no frontend framework. Two surfaces:
- **Customer-facing**: `index.html` (landing page — collections, a 3-card contact strip for Chat/WhatsApp/Email, a gluten-free/allergy/religious-certification policy strip, footer with a discreet Staff Login link) → `templates.html` → `designer.html` → `order-review.html` → `customer-information.html` (with the mandatory, not-prechecked allergy confirmation checkbox) → `payment.html` (simulated payment) → `confirmation.html`. The same compact policy strip (gluten-free / allergy confirmation / no religious certification) appears on `templates.html`, `designer.html`, `order-review.html`, and `customer-information.html`, so the policy stays visible throughout the ordering journey, not only at checkout. A floating chat widget (`chat-widget.js`) is present on every customer page and also supports full chat-assisted ordering.
- **Admin/backoffice**: `admin-login.html`, `admin-dashboard.html`, `admin-orders.html` (order list + detail drawer with Order Details / Payment / Production Status / Update Status / Customer Update sections), `admin-customers.html`, `admin-customer-detail.html`, `admin-notifications.html` (the Communications Workspace) — all behind authentication.

Deployed as a static site on **Railway** (service `cakecraft-studio`, `cakecraft-studio-production.up.railway.app`) — this is the authoritative, live production frontend. It calls the FastAPI backend over REST.

## 5. Backend / API

FastAPI (Python), organized under `backend/app/api/routes/`: customer-facing routes (`orders.py`, `templates.py`, `designer.py`, `collections.py`, `chat.py` — both website Q&A and chat-assisted ordering), admin routes under `admin/` (`orders.py`, `customers.py`, `notifications.py`, `communications.py`, `agent.py`, `rag.py`, `briefing.py`, `catalog.py`, `auth.py`, `dashboard.py`), and two public webhook routes: `webhooks.py` (Meta WhatsApp Cloud API and Gmail-related webhooks, not currently the live WhatsApp path — see §11) and `webhooks_twilio.py` (`POST /webhooks/twilio-whatsapp` — the live inbound WhatsApp path). Routes are thin — they validate input, call into the service layer, and translate exceptions into HTTP responses; business logic lives one layer down.

## 6. Service Layer

`backend/app/services/` — one module per business domain: `order_service.py`, `payment_service.py` (simulated payment), `customer_service.py`, `notification_service.py` + `notification_templates.py`, `agent_service.py` (the AI Agent — chat Q&A, chat-assisted ordering, AI Operations Agent, reply drafting), `rag_service.py`, `forecast_service.py` (ML demand forecasting), `briefing_service.py` (structured daily-briefing data), `inbound_service.py` (inbound-message orchestration across Email/WhatsApp/Chat/order-notes), `communication/` (Resend/Gmail and Twilio/Meta WhatsApp adapters, plus their inbound counterparts), `audit_service.py`, `auth_service.py`, `dashboard_service.py`, `template_service.py`, `designer_service.py`, `collection_service.py`. Services talk to Supabase directly; routes never do.

## 7. Database / Supabase

Postgres via Supabase, `pgvector` extension enabled for RAG embeddings. 20 forward-only migrations applied in production. Core tables: `bakery`, `cake_templates`, `cake_sizes`/`flavors`/`fillings`/`frostings` (designer options), `customers`, `orders`, `payments` (simulated/demo payment records — see §16), `notifications`, `inbound_messages`, `knowledge_documents`, `staff_profiles`, `audit_log`. Migrations are never edited after being applied — a correction is always a new migration (e.g. `correct_bakery_email_to_2002`, a real example of this discipline). Live production data as of this document: 2,634 orders, 2,027 customers, 9,608 notifications, 118 inbound messages.

## 8. AI / Claude Integration

Anthropic's Claude (model `claude-sonnet-5`) is used for: (1) drafting customer-facing reply language grounded in retrieved knowledge and order context (Email/WhatsApp/Chat Q&A), (2) chat-assisted order-taking (extracting selections, judging confirmation — always validated by the application, never trusted directly), and (3) synthesizing operational summaries and answering ad-hoc operational questions for staff (the AI Operations Agent — see §9). Full detail on the authority boundary between what Claude decides and what the application decides is in `docs/AI_RAG_AND_SAFETY.md`.

## 9. AI Operations Agent

A staff-facing capability (`agent_service.py`, routes under `admin/agent.py`), distinct from the customer-facing reply drafting above: a synthesized **morning briefing** narrative built on top of the structured daily briefing (`briefing_service.py`) and the ML forecast (§10); an **ask-a-question** endpoint ("what should I prepare tomorrow?") combining live operational data, the forecast, and retrieved bakery knowledge; and **on-demand communication drafting** for a specific order, which — like every other AI-produced message in this project — only ever creates a `draft` notification for a human to review, never sends anything itself.

## 10. ML Forecasting

`forecast_service.py` — a Random Forest regressor (scikit-learn), retrained fresh on every call (well under a second on the current ~360 rows of daily history, so no staleness or model-versioning step is needed). Random Forest was selected after a documented comparison against XGBoost, LightGBM, and CatBoost on the same engineered feature set (calendar signals, lag/rolling-window order history, confirmed-orders-for-date), evaluated with a time-based train/test split (`tools/evaluate_forecast_models.py`) — it won or tied on every metric for both targets (order volume, revenue) at the lowest deployment weight, with a natural uncertainty measure (spread across its own trees) that directly powers the forecast's Explainable-AI confidence score and plain-English "why" (via `feature_importances_`, translated to human-readable labels, never raw feature names).

## 11. RAG Architecture

A deliberately simple retrieval design for this project's scale: `TfidfVectorizer` (scikit-learn) fit once across the whole `knowledge_base/*.md` corpus (16 documents, 88 indexed chunks as of this document), embeddings stored in `knowledge_documents.embedding` (`pgvector`), retrieved via cosine-distance similarity through a Postgres RPC (`match_knowledge_documents`). See `docs/AI_RAG_AND_SAFETY.md` for the retrieval process, the knowledge boundary, and an honestly-documented retrieval limitation found during testing.

## 12. Email Integration

Implemented and **live-verified end-to-end**. **Outbound** goes through **Resend's HTTPS API** (`communication/gmail_adapter.py` — filename kept, transport changed), not raw SMTP: Railway blocks outbound SMTP ports entirely at the network level (confirmed by direct in-container testing — ports 25/465/587/2525 to `smtp.gmail.com` all silently time out, while HTTPS egress works instantly), so SMTP could never have delivered mail from this host. Resend sends from its own shared sandbox address with `Reply-To` set to the real business address, `mybestcake2002@gmail.com`, so customer replies land correctly. **Inbound** is unaffected by that change and still runs via a background IMAP-polling task (`communication/gmail_inbound.py`) started in `app.main`'s FastAPI lifespan on every deploy, plus an on-demand "check now" admin action.

## 13. WhatsApp Integration

Implemented via the **Twilio WhatsApp Sandbox** (`communication/twilio_whatsapp_adapter.py` outbound, `communication/twilio_whatsapp_inbound.py` + `app/api/routes/webhooks_twilio.py` inbound, `POST /webhooks/twilio-whatsapp`) — this project's actual, live WhatsApp integration, not the Meta Cloud API. A separate, independently complete Meta Cloud API adapter (`whatsapp_adapter.py`, `whatsapp_inbound.py`, the `webhooks.py` route) also exists in the codebase and is unit-tested, but is not the one currently configured/live; `communication/__init__.py`'s `_register_whatsapp_provider()` selects Twilio automatically whenever it's configured, which it is in production.

- **Outbound**: real HTTP calls to Twilio's Messages API, correct credentials, correct Sandbox "From" number — verified directly against Twilio's own Message-status API.
- **Inbound**: the webhook route is deployed, publicly reachable, and correctly parses Twilio's real payload shape (`From`/`To`/`Body`/`MessageSid`) after verifying `X-Twilio-Signature` via Twilio's own `RequestValidator`.
- **Known external limitation (Sandbox configuration, not a code defect)**: Twilio's Sandbox "When a message comes in" webhook URL is a Console-only setting (confirmed: no REST API exposes it for this account/product) and is not currently pointed at CakeCraft's webhook, so Twilio currently answers inbound Sandbox messages with its own built-in default responder instead of forwarding them to `/webhooks/twilio-whatsapp`. A real customer WhatsApp message reaching Twilio was independently confirmed via Twilio's own message log. This is a one-time manual Console action, not an application gap — see `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` §5 for the full, honest status.
- **Outbound free-form/24-hour-window limitation**: the adapter always sends free-form `Body` text (no Message Template support), which WhatsApp only permits within an open 24-hour customer-service session — a proactive/automated message to a customer with no recent inbound message from them will be rejected by WhatsApp (`error 63016`), independent of the Sandbox webhook issue above.

## 14. Authentication / Authorization

Supabase Auth issues sessions for staff (`staff_profiles`, role-based — an `admin` role and at least one other staff role exist). Every admin route depends on `get_current_admin` (any active staff session) or, for the small number of actions that specifically require elevated trust, `require_role("admin")`. No admin route is unauthenticated; the public site and the two webhook endpoints (Twilio, Meta) are the only unauthenticated surfaces, and both webhooks are independently protected by signature verification (Twilio: HMAC-SHA1 over the full URL + params via Twilio's own validator; Meta: HMAC-SHA256 over the raw body). The public-facing website also links to `admin-login.html` via a small, deliberately unobtrusive "Staff Login" footer link — this exposes no new surface; it is the same existing authenticated login.

## 15. Chat-Assisted Ordering

A slot-filling ordering flow inside the same customer-facing chat widget used for Q&A (`agent_service.run_order_assistant_turn`, `POST /chat/order`). Claude extracts/updates the customer's selections turn by turn from free text, matched only against real catalog ids (an id Claude invents is ignored, never trusted); a deterministic Python helper resolves cake size directly from a stated guest count. **Order creation is gated by three independent checks**, not by Claude's own judgment alone: Claude's own `confirmedNow` signal, every required field (design, size, flavor, filling, frosting, phone) actually known, and a fixed keyword check on the customer's raw message (so a misclassified "confirmedNow" alone can never create a real order). A message mentioning a food allergy at any point deterministically blocks order creation before Claude is even called (see `docs/AI_RAG_AND_SAFETY.md` §16), and the mandatory allergy confirmation is folded into the same final "shall I place this order?" ask once every other field is known. On success, the order is created through the exact same `order_service.create_order()` the website Designer flow uses — there is no parallel creation path.

## 16. Simulated Payment

`payment_service.py` — a demo-only payment simulation; there is no real card data or real payment provider anywhere in this project. `payments` is its own table, linked to `orders`. A successful simulated payment **automatically** transitions the order from `pending` to `confirmed` — this is deterministic application logic, not an AI decision and not a staff action. See §17 for the full order lifecycle and how this interacts with the staff-driven production stages.

## 17. Order Lifecycle

Two related but distinct concepts, intentionally kept separate:

- **Payment status** (on the `payments` record): `pending` / `paid` / `failed`.
- **Production/order status** (`orders.status`, a fixed 6-value enum enforced by both a database check constraint and application code): `pending` → `confirmed` → `in_progress` → `ready` → `completed`, with `cancelled` reachable from any **non-terminal** status (`pending`, `confirmed`, `in_progress`, `ready`) — `completed` and `cancelled` are both terminal; no further transition is allowed out of either.

`pending → confirmed` happens **automatically**, the moment a simulated payment succeeds — a normal, catalog-valid order never requires manual staff approval to reach `confirmed`. Every transition from `confirmed` onward (`in_progress`, `ready`, `completed`, or a cancellation) is a **deliberate staff action** in the Admin Orders drawer, validated against a fixed transition graph (skipping a stage or moving backward is rejected; re-saving the current status is a harmless no-op). Full detail, including the exact notification event fired at each transition, is in `docs/ORDER_JOURNEY_AND_DEMO.md`.

## 18. Notifications

See `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` for the full notification state machine, channel model, and idempotency design.

## 19. Communications Workspace

The admin-facing single screen (`admin-notifications.html`) for reviewing, editing, and sending every outbound communication — AI-drafted replies, order-status drafts, and on-demand AI Agent drafts — through one shared list, filter set, and detail drawer, plus a WhatsApp conversation-thread view and a Twilio/Meta status banner. Documented in `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md`.

## 20. Back Office / Dashboard

`admin-dashboard.html` — a read-only aggregate view (`dashboard_service.py`) plus the AI Operations Agent's morning briefing and the ML forecast (§9, §10), giving staff one place to see today's operational picture and tomorrow's prediction.

## 21. Customers / CRM

`admin-customers.html` / `admin-customer-detail.html` — customer list/search, profile, order history, and a chronological Customer Timeline (`customer_service.get_customer_timeline`) merging order-placement events, audited status changes, and every notification into one view. Two panels on the customer-detail screen — **Customer Communications history** and **AI Insights** — are still explicit, gracefully-degrading placeholders (`{"enabled": False, ...}`) even though the underlying data/capability now exists elsewhere in the app (the Communications Workspace, the AI Operations Agent); wiring them up was identified in the Final Project Gap Audit as a small, backend-ready remaining item, not attempted here.

## 22. Deployment Architecture

Two Railway services in one project: `web` (the FastAPI backend, `web-production-c9dd99.up.railway.app`) and `cakecraft-studio` (the static frontend, `cakecraft-studio-production.up.railway.app`) — this is the authoritative production frontend; there is no Netlify deployment. Both services auto-deploy on every push to `main`. Supabase is the managed Postgres/Auth provider. Both Railway services were confirmed **RUNNING** during final validation, most recently after this documentation refresh.

## 23. External Integrations

| Integration | Status |
|---|---|
| Supabase (Postgres, Auth, pgvector) | Implemented, live |
| Anthropic Claude | Implemented, live |
| Email — Resend (outbound) + Gmail IMAP (inbound) | Implemented, live, end-to-end verified with a real email |
| WhatsApp — Twilio Sandbox | Outbound adapter and inbound webhook implemented and deployed; outbound verified directly against Twilio; inbound blocked by an external Sandbox Console configuration gap (see §13) |
| WhatsApp — Meta Cloud API | Implemented, unit-tested, present in the codebase as an alternate adapter; not the currently configured/live provider |
| Railway (hosting) | Live, both services `RUNNING` |

## 24. Security Boundaries

- Admin routes: authenticated (`get_current_admin`), with a small number of actions additionally role-checked (`require_role("admin")`).
- The two public webhooks (Twilio WhatsApp, Meta): unauthenticated by necessity (they're public callback URLs), but every request is signature-verified before any content is trusted or processed.
- Secrets (`GMAIL_APP_PASSWORD`, `GMAIL_ADDRESS`, `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, Supabase keys) live only in Railway environment variables — never in source, never logged, never returned in any API response.
- Customer data isolation: the AI reply-drafting function receives exactly one customer/order pair as arguments — there is no code path that could pull in another customer's data.
- **Security response headers** (Final Security Hardening Pass): the backend (`app.main`'s `add_security_headers` middleware) attaches `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, a maximally restrictive `Content-Security-Policy` (`default-src 'none'`, appropriate for a JSON/TwiML-only API), and `Strict-Transport-Security` to every response. The frontend (`frontend/serve.json`, read automatically by the `serve` static file server) attaches the same headers to every page/asset, plus a real `Content-Security-Policy` scoped to what the application actually loads (`'self'` for scripts/images, `fonts.googleapis.com`/`fonts.gstatic.com` for Google Fonts, and the backend's own origin for `connect-src`) — verified locally against real running instances of both services before deploying. CORS remains `allow_origins=["*"]`/`allow_credentials=False`: reviewed and deliberately left unchanged (safe given no cookie-based session exists; restricting it risked breaking a legitimate access pattern this app doesn't fully control from here — see the code comment at the CORS middleware itself for the full reasoning).
- **Dependency security**: `cryptography` and `h2` were upgraded (50.0.0, 4.4.1) during the Final Security Hardening Pass, resolving the two CVEs the audit found (neither was exploitable via this app's actual usage, but both were safely upgradable with zero dependency conflicts). `pip-audit` against the current `backend/requirements.txt`: 0 known vulnerabilities. See `docs/DEPENDENCIES_AND_LICENSES.md`.

## 25. AI Bakery Manager (optional, additive)

An optional automation layer over the same deterministic services the human manager already uses — the manual Back Office (Dashboard, Orders, Communications, status changes) remains complete, unchanged, and the primary way to run the bakery. This feature never replaces it and nothing else in the application depends on it.

**Architecture:**

> CakeCraft separates deterministic business logic from AI. Authentication, authorization, pricing, payment, order-state transitions, and safety validation are controlled by application logic. AI is used for assistance, forecasting interpretation, grounded knowledge, and communication drafting — not as the authority over critical business operations. The AI Manager has autonomy only within explicitly defined operational boundaries: it may propose actions, but deterministic CakeCraft services remain the authority over whether an action is allowed and how it is executed.

> The autonomous agent is an optional orchestration layer over the same deterministic services used by the human manager. It augments the Back Office; it does not replace it.

A thin new orchestration service (`bakery_manager_service.py`) — distinct from the AI Operations Agent (`agent_service.py`, unchanged), which produces analysis for a human to read; this produces a structured, approvable plan. Both share the same Claude-calling pattern and the same `briefing_service`/`forecast_service`/`rag_service` data sources; nothing is duplicated.

**Preview Plan** (`POST /admin/bakery-manager/preview`, any authenticated staff, fully read-only): gathers live orders/forecast/policy deterministically, makes exactly one Claude call to produce a structured plan, then independently re-classifies every proposed action against `order_service`'s own transition graph and a deterministic production-timing rule — Claude's own opinion is never trusted, only ever downgraded. Nothing is written except one audit log entry.

**Execute Approved Plan** (`POST /admin/bakery-manager/execute`, `admin` role only): the manager's checkbox-selected actions only, each independently re-validated from scratch against the live database (the round-tripped plan is treated as untrusted client input) before calling the exact existing service a human action would call. Zero Claude calls; no direct database writes from this module.

**Executable in V1**: `confirmed → in_progress`, only when the order has a real `pickup_date` and it's within the same "due soon" window `app/services/priority_service.py` (see below) computes as CRITICAL/HIGH; creating a customer-update draft (`notification_service.create_notification_for_order_event`, same idempotency as the manual path); creating a staff-note draft (`notification_service.create_staff_message`). **Recommendation-only**: `in_progress → ready` and `ready → completed` (no system field proves physical decoration completion or actual customer pickup), production reprioritization, staffing/inventory observations. **Never proposed as a tool at all**: payment, price, refunds, cancellation, catalog, customer PII, allergy/religious exceptions, or any real Email/WhatsApp send.

Audit: reuses `audit_service.record_event()` exclusively (no second audit log) — `agent.plan_generated` once per Preview, `agent.action_executed`/`agent.action_rejected`/`agent.action_failed` once per Execute action.

UI: one additional card on `admin-dashboard.html`, alongside the existing AI Daily Briefing/Ask Agent/RAG cards — none of them altered. Each proposed `advance_to_in_progress` action now also carries its `priority_service` label (CRITICAL/HIGH) and reason as evidence, purely informational.

### Deterministic Order Priority (Pickup Date + Order Priority, Phase 1 & 2)

`app/services/priority_service.py` is a small, pure, Claude-free module — `compute_priority(order)` returns a `CRITICAL`/`HIGH`/`NORMAL`/`LOW` label (or `None` + `manager_attention=True` for a missing pickup date, never guessed into a level) from ordinary Python business rules over existing order facts (status, pickup date, category). The same order always produces the same priority. It is the one shared source of truth consumed by three places: the Back Office Orders list/drawer (a read-only badge, server-computed — never calculated in JavaScript), the AI Bakery Manager (both its `confirmed → in_progress` eligibility bound and the priority evidence shown in Preview), and the RAG knowledge base (`knowledge_base/production_workflow.md`'s "Order Priority Levels" section, which documents — never computes — the same policy). Priority is decision support only: it never changes an order's status, never authorizes an AI Bakery Manager action by itself, and never sends anything.

Pickup scheduling: the Website order form (`customer-information.html`) now requires a desired pickup date/time for every new order, validated authoritatively server-side (`order_service.validate_pickup_datetime` — past date, Monday, and outside 9 AM–6 PM are all hard-rejected; a date inside a collection's normal lead time is accepted and flagged as a soft "rush" note, never silently blocked or promised). Chat-assisted ordering (`agent_service.run_order_assistant_turn`) captures a stated pickup date/time opportunistically, independently re-validated the same way, but never as a hard requirement to confirm — kept deliberately additive so the existing, heavily-tested chat confirmation flow stays unchanged. Historical orders created before this field existed keep `pickup_date = NULL` — never backfilled or guessed; they display as `NEEDS INFO` in both the Back Office and the AI Bakery Manager's exceptions, by design.

### Servings + Event Pricing

`app/services/serving_band_service.py` is another small, pure, Claude-free module — `compute_serving_band(guest_count)` deterministically returns `SMALL`/`MEDIUM`/`LARGE`/`XL`/`EVENT` (8–75 guests) or `CUSTOM_EVENT` (76+), and `is_standard_ordering_eligible()` is the one authoritative gate for standard automated checkout. Guest count, not a customer-picked size, is the primary business input: `order_service.create_order()` independently derives the correct size (and therefore price) from `guest_count` whenever it's present, ignoring whatever `cake_size_id` was also submitted — this is what makes the rule impossible to bypass via a crafted direct POST, not just a frontend convenience. A celebration of more than 75 guests is never automatically priced and can never reach standard checkout/payment on any channel (Website route, Chat, or a direct API call); the customer is guided to contact the bakery for a tailored proposal instead — by **phone (+972 54-544-6601) or email only**, deliberately never the Twilio Sandbox WhatsApp number (a separate technical/demo integration, not the Custom Event escalation channel) — with the exact same approved wording and contact options on the Designer, Order Review (which independently re-derives size from `guestCount` the same way, so a stale/tampered URL can't present a mismatched standard order as valid either), the Chat widget's own opening notice, and `knowledge_base/pricing_policy.md`. Five standard sizes now exist in `cake_sizes` (Small through Event, +$0 to +$200 in a consistent +$50-per-tier scale); guest count is stored in the existing `orders.configuration` JSON, not a new column. Claude never calculates a serving band or a price — Chat only ever reads this module's output, the same "propose, Python decides" boundary as pickup scheduling and priority above. The Designer's serving guide lists only the five standard bands; the 76+ case is explained once, in the adjacent Custom Event notice, not duplicated as a table row.

## 26. Human-in-the-Loop Design

The architectural centerpiece of this project. See `docs/AI_RAG_AND_SAFETY.md` and `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` for full detail. In one sentence: **Claude drafts; the application decides whether that draft needs a human's attention, and only a human's explicit click can ever cause a real send — automatically-created order-status drafts and simulated payment's own automatic `pending → confirmed` transition are both deterministic application logic, never an AI decision.**
