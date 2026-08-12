# CakeCraft Studio — Final Architecture

**Status: CURRENT / AUTHORITATIVE.** This document describes the system as it exists in the submitted project, verified against the actual code and a live test suite (242/242 passing) at the time of writing. For the project's development history, see the sprint documents listed in `docs/README.md`.

## 1. Project Purpose

CakeCraft Studio ("Maison de Gâteau Paris") is a custom-cake ordering platform built to demonstrate a realistic, end-to-end application of modern software engineering practice: a layered web application, a real external communication integration (Gmail), an AI/RAG-assisted customer communication layer, and — the project's central engineering contribution — a human-in-the-loop safety architecture where AI can draft customer communication but can never send it unsupervised.

## 2. Academic / Demo Scope

This is a final-degree academic project, not a commercial product. It uses a realistic bakery scenario to demonstrate the architecture; it is not intended to operate as a real business, does not process real payments, and its "customers" are synthetic demo records except where noted (see `docs/TESTING_AND_VALIDATION.md` for what was validated with real, live infrastructure vs. automated tests).

## 3. System Overview

```text
                          Customer
                             │
                             ▼
                ┌─────────────────────────┐
                │         Frontend         │
                │   HTML • CSS • JS (static)│
                └────────────┬─────────────┘
                             │ REST API
                             ▼
                ┌─────────────────────────┐
                │      FastAPI Backend     │
                │       Route Layer        │
                └────────────┬─────────────┘
                             │
                             ▼
                ┌─────────────────────────┐
                │       Service Layer      │
                ├───────────┬─────────────┤
                │  Orders   │  Customers   │
                │Notifications│ AI Agent   │
                │    RAG    │ Communication│
                │           │  Adapters    │
                └─────┬─────┴──────┬───────┘
                      │            │
                      ▼            ▼
              ┌───────────┐  ┌───────────────┐
              │ Supabase  │  │ Communication  │
              │ Postgres  │  │   Adapters     │
              │  + Auth   │  │ ┌─────┬───────┐│
              │  + pgvector│  │ │Gmail│WhatsApp││
              └───────────┘  │ └─────┴───────┘│
                              └───────────────┘
```

The AI communication path (Gmail/WhatsApp inbound → customer reply) is a distinct flow through the same service layer:

```text
Inbound Message (Email or WhatsApp)
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
RAG Retrieval (CakeCraft knowledge base)
        │
        ▼
Claude (drafts language, classifies intent, self-reports confidence)
        │
        ▼
Application Guardrails (app-owned risk tier — see AI_RAG_AND_SAFETY.md)
        │
        ▼
Draft Notification (status = draft)
        │
        ▼
Human Review → Admin Approval → Send
```

## 4. Frontend

Static HTML/CSS/vanilla JavaScript, no build step, no frontend framework. Two surfaces:
- **Customer-facing**: `index.html` → `templates.html` → `designer.html` → `order-review.html` → `customer-information.html` → `confirmation.html` — the cake-design and order-submission flow.
- **Admin/backoffice**: `admin-login.html`, `admin-dashboard.html`, `admin-orders.html`, `admin-customers.html`, `admin-customer-detail.html`, `admin-notifications.html` (the Communications Workspace) — behind authentication.

Deployed as a static site on Railway (see §17), calling the FastAPI backend over REST.

## 5. Backend / API

FastAPI (Python), organized under `backend/app/api/routes/`: customer-facing routes (`orders.py`, `templates.py`, `designer.py`, `collections.py`), admin routes under `admin/` (orders, customers, notifications, communications, agent), and `webhooks.py` (WhatsApp's public Meta webhook endpoint). Routes are thin — they validate input, call into the service layer, and translate exceptions into HTTP responses; business logic lives one layer down.

## 6. Service Layer

`backend/app/services/` — one module per business domain: `order_service.py`, `customer_service.py`, `notification_service.py` + `notification_templates.py`, `agent_service.py` (the AI Agent), `rag_service.py`, `inbound_service.py` (inbound-message orchestration), `communication/` (Gmail and WhatsApp adapters, plus their inbound counterparts), `audit_service.py`, `auth_service.py`. Services talk to Supabase directly; routes never do.

## 7. Database / Supabase

Postgres via Supabase, `pgvector` extension enabled for RAG embeddings. Core tables: `bakery`, `cake_templates`, `cake_sizes`/`flavors`/`fillings`/`frostings` (designer options), `customers`, `orders`, `notifications`, `inbound_messages`, `knowledge_documents`, `staff_profiles`, `audit_log`. All migrations are forward-only, never edited after being applied — a correction is always a new migration (see the two email-identity-correction migrations in `supabase/migrations/` as a real example of this discipline in practice).

## 8. AI / Claude Integration

Anthropic's Claude (model `claude-sonnet-5`) is used for two distinct capabilities: (1) drafting customer-facing reply language grounded in retrieved knowledge and order context, and (2) synthesizing operational summaries for staff (the AI Operations Agent / morning briefing). Full detail, including exactly what Claude is and is not trusted to decide, is in `docs/AI_RAG_AND_SAFETY.md`.

## 9. RAG Architecture

A deliberately simple retrieval design for this project's scale: `TfidfVectorizer` (scikit-learn) fit once across the whole `knowledge_base/*.md` corpus, embeddings stored in `knowledge_documents.embedding` (`pgvector`), retrieved via cosine-distance similarity through a Postgres RPC (`match_knowledge_documents`). See `docs/AI_RAG_AND_SAFETY.md` for the retrieval process, the knowledge boundary, and an honestly-documented retrieval limitation found during testing.

## 10. Gmail Integration

Implemented and **live-verified**: inbound via IMAP polling (`communication/gmail_inbound.py`), outbound via SMTP (`communication/gmail_adapter.py`). A real end-to-end round trip (inbound detection → AI draft → human approval → SMTP send → recipient confirmation) was completed successfully — see `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` for details. Official address: `mybestcake2002@gmail.com`.

## 11. WhatsApp Integration

**Implemented, not live-demonstrated.** Inbound webhook (`communication/whatsapp_inbound.py`, with real HMAC-SHA256 signature verification against Meta's `X-Hub-Signature-256` header) and outbound adapter (`communication/whatsapp_adapter.py`, Meta Cloud API) are both code-complete and unit-tested, sharing the exact same downstream pipeline (customer matching → RAG → Claude → guardrails → draft → approval) as Gmail. Live delivery was not exercised because it requires real Meta Business API credentials, which were not provisioned for this project. This is a configuration gap, not a code gap.

## 12. Authentication / Authorization

Supabase Auth issues sessions for staff (`staff_profiles`, role-based: at minimum an `admin` role exists). Every admin route depends on `get_current_admin` (any active staff session) or, for the one action that specifically requires elevated trust — approving a notification — `require_role("admin")`. No admin route is unauthenticated; the public site and the Meta webhook endpoint are the only unauthenticated surfaces, and the webhook is independently protected by signature verification.

## 13. Notifications

See `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` for the full notification state machine, channel model, and idempotency design.

## 14. Communications Workspace

The admin-facing single screen (`admin-notifications.html`) for reviewing, editing, and approving every outbound communication — both AI-drafted replies and deterministic order-status drafts — through one shared list, filter set, and detail drawer. Documented in `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md`.

## 15. Customer Timeline

A per-customer chronological feed (`customer_service.get_customer_timeline`) merging order-placement events, audited status changes, and every notification (at whatever stage) into one view, reachable from the Customer Detail admin screen.

## 16. Order Lifecycle

`pending → confirmed → in_progress → ready → completed`, with `cancelled` reachable at any point. Full detail, including the exact notification event fired at each transition, is in `docs/ORDER_JOURNEY_AND_DEMO.md`.

## 17. Deployment Architecture

Two Railway services in one project: `web` (the FastAPI backend, `web-production-c9dd99.up.railway.app`) and `cakecraft-studio` (the static frontend, `cakecraft-studio-production.up.railway.app`). Supabase is the managed Postgres/Auth provider. Both Railway services were confirmed **Online** and reachable during final validation.

## 18. External Integrations

| Integration | Status |
|---|---|
| Supabase (Postgres, Auth, pgvector) | Implemented, live |
| Anthropic Claude | Implemented, live |
| Gmail (IMAP + SMTP) | Implemented, live, end-to-end verified with a real email |
| WhatsApp Business Cloud API (Meta) | Implemented, unit-tested, not live-demonstrated (no Meta credentials) |
| Railway (hosting) | Live, both services online |

## 19. Security Boundaries

- Admin routes: authenticated, role-checked where the action warrants it (approval).
- The Meta webhook: unauthenticated by necessity (it's a public callback URL), but every request is HMAC-signature-verified against the raw body before any content is trusted or processed.
- Secrets (`GMAIL_APP_PASSWORD`, `WHATSAPP_ACCESS_TOKEN`, `ANTHROPIC_API_KEY`, Supabase keys) live only in Railway environment variables — never in source, never logged, never returned in any API response.
- Customer data isolation: the AI reply-drafting function receives exactly one customer/order pair as arguments — there is no code path that could pull in another customer's data.

## 20. Human-in-the-Loop Design

The architectural centerpiece of this project. See `docs/AI_RAG_AND_SAFETY.md` and `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` for full detail. In one sentence: **Claude drafts; the application decides whether that draft needs a human, and only a human's explicit approval can ever cause a real send.**
