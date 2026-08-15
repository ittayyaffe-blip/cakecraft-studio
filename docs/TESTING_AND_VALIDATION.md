# Testing & Validation

**Status: CURRENT / AUTHORITATIVE.** Reflects the current validated state of the repository and the deployed application — verified by actually running the suite and by live, read-only production checks, not carried over from an earlier count.

## 1. Two Distinct Forms of Evidence

This project's validation deliberately separates two things that are easy to conflate: automated tests that run without any external dependency, and manual/live checks against the real deployed application and real external services. Both matter; neither substitutes for the other. Automated tests prove the logic is correct in isolation and stays correct as the code changes; manual/live validation proves the real integrations (Twilio, Gmail/Resend, Supabase, Claude, Railway) actually work together in production, which no amount of mocking can prove on its own.

## 2. Automated Validation — 470/470 Passing

Run via `pytest` from `backend/` (`python -m pytest`). Every test module is dependency-free — no live network/DB/Twilio/Anthropic call — mocking each external boundary at its exact call site while running the real business logic around it.

| Module | Checks | Covers |
|---|---|---|
| `test_agent_service` | 87 | AI Agent orchestration: intent/handling classification, guardrail scenarios (allergy, religious, discount, refund, complaint, legal threat, privacy, prompt injection), order-vs-RAG authority, conversation context, the deterministic Website-First fast path, Chat-vs-WhatsApp/Email reply differentiation, payment-status grounding |
| `test_agent_order_assistant` | 62 | Chat-assisted ordering: catalog id validation, the size-regression fix, the triple order-confirmation gate, the deterministic food-allergy safety gate, WhatsApp/Chat parity |
| `test_communication_adapters` | 48 | Resend(email)/Meta WhatsApp/Twilio WhatsApp adapter contracts, unconfigured-adapter fallback, WhatsApp provider selection precedence |
| `test_notification_service` | 35 | State-machine transition guards, `(order_id, event)` idempotency, template rendering (incl. conditional pickup-date inclusion, never invented), WhatsApp-vs-email channel preference |
| `test_inbound_service` | 34 | Inbound message deduplication, customer/order matching, conversation-history scoping, WhatsApp assisted-order-continuation retirement (Website-First policy) |
| `test_template_service` | 19 | Catalog template read logic |
| `test_twilio_whatsapp_inbound` | 18 | Twilio webhook signature verification (`RequestValidator`), payload parsing |
| `test_admin_catalog` | 18 | Admin catalog management (templates, activation) |
| `test_order_service_admin` | 17 | Production-stage transition validation (the fixed transition graph), admin order listing |
| `test_whatsapp_inbound` | 15 | Meta Cloud API webhook signature verification, payload parsing |
| `test_payment_service` | 13 | Simulated payment lifecycle, idempotency, the automatic `pending → confirmed` transition |
| `test_orders_route` | 13 | Order-creation route: the "order received" draft trigger (never blocks creation if it fails), the order-notes inbound-pipeline hook, background notification scheduling |
| `test_forecast_service` | 12 | ML demand forecasting |
| `test_gmail_inbound` | 11 | Email parsing, threading |
| `test_customer_service` | 11 | Customer search/matching |
| `test_rag_service` | 9 | Embedding padding/consistency, zero-vector short-circuit, grounded-answer orchestration |
| `test_webhooks_twilio_route` | 8 | Real-HTTP coverage of the Twilio webhook route itself (signature enforcement, response shape) |
| `test_chat_route` | 8 | Chat route: customer identification/creation, server-derived order context (ignores any client-supplied order id), blank-question rejection |
| `test_security_dependencies` | 7 | Role-based route protection |
| `test_order_service` | 7 | `create_order()`'s own id-validation/pricing/payload-building logic |
| `test_briefing_service` | 7 | Operational briefing synthesis |
| `test_admin_communications_route` | 7 | Admin WhatsApp thread/reply routes |
| `test_admin_notifications_route` | 4 | Notification list `?channel=` filter validation |
| **Total** | **470** | |

## 3. Manual / Live End-to-End Validation

Not automated (by design — these exercise real external services, real credentials, and the real deployed application, deliberately outside the fast/dependency-free test suite):

- **Website ordering journey**: a real order taken end-to-end through Templates → Designer → Order Review → Customer Information → simulated Payment → Confirmation on the live deployed frontend, with the order landing correctly in the Admin Orders list.
- **Simulated payment**: a real Pay Now click on the live application; the order transitioned `pending → confirmed` automatically, with no staff action required.
- **Production lifecycle (staff-driven)**: a real order manually walked through `Confirmed → In Progress → Ready → Completed` in the Admin Orders drawer on the live deployed application. Each staff-driven stage change was confirmed to generate the correct customer-communication **draft** for review in the Communications Workspace, with a working "Review in Communications" deep link — none was auto-sent.
- **Email**: a real inbound email, detected by the real IMAP poller; a real customer identified from its sender address; real RAG retrieval and a real Claude-drafted reply; a real draft → Send → real Resend delivery, with the recipient personally confirming receipt (correct sender, subject, and body).
- **WhatsApp — outbound**: real HTTP calls to Twilio's Messages API, verified directly against Twilio's own Message-status API (correct recipient, correct Sandbox "From" number, correct credentials).
- **WhatsApp — inbound**: a real customer WhatsApp message reaching Twilio was independently confirmed via Twilio's own message log (`status: received`, real Message SID, real body, real timestamp). **CakeCraft's own inbound routing (Twilio → our webhook → `inbound_messages` → Communications Inbox) has NOT been demonstrated end-to-end** — Twilio is not currently configured to call our webhook at all (an external Sandbox Console setting, not a code defect; see `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` §5). Do not read this document, or any other, as claiming that path passed.
- Both Railway services (`web`, `cakecraft-studio`) confirmed `RUNNING` and reachable; Supabase connectivity confirmed via live, read-only queries.

## 4. Known Non-Blocking Limitations

Presented honestly, as limitations and future-improvement candidates — not as failures:

- **WhatsApp inbound routing is currently blocked by an external Twilio Sandbox configuration gap** (§3, above) — the one remaining manual step is a Console setting, not application code; see `docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md` §5 for the full, honest status.
- **WhatsApp outbound is free-form only** (no Message Template support), so a proactive/automated message to a customer with no recently-open 24-hour session is rejected by WhatsApp (`error 63016`) — observed live and documented, not a hidden gap.
- **Notification idempotency is enforced at the application level**, not by a database uniqueness constraint. This is an intentional choice for this academic project's scale (a single-admin-operator system, not a high-concurrency production service) — a genuine race between two simultaneous requests remains theoretically possible. A `unique` constraint on `notifications(order_id, event)` was identified as the stronger alternative and would be a small, additive migration if ever needed.
- **Failed-send error messages are not persisted** on the notification record itself — a `failed` status is visible to staff, but the specific delivery error is only in server logs, not the UI. Identified as an optional future improvement.
- **RAG retrieval is not perfect.** A real, observed case is documented in `docs/AI_RAG_AND_SAFETY.md`: a birthday-cake recommendation question did not retrieve the most relevant knowledge document. The system's safety behavior in that case was correct (it escalated rather than guessed), but this is disclosed as a genuine retrieval-quality limitation of the TF-IDF approach, not claimed away.
- **Two Customer-detail panels (Communications history, AI Insights) are still explicit placeholders** — see `docs/FINAL_ARCHITECTURE.md` §21. They degrade gracefully (a styled "not enabled yet" state, not an error); identified as a small, backend-ready remaining item, not a defect.

## 5. What Was Deliberately Not Re-Tested

Per the project's own safety rules during later development/documentation phases: no second real production order, payment, email, or WhatsApp message was created purely to re-demonstrate something already proven — later validation and diagnostics reused existing evidence (real orders, real Twilio message logs, real Supabase records) rather than repeating a live send/order/payment merely for demonstration purposes.
