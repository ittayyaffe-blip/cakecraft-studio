# Testing & Validation

**Status: CURRENT / AUTHORITATIVE.** Reflects the final validated state of the submitted project.

## 1. Two Distinct Forms of Evidence

This project's validation deliberately separates two things that are easy to conflate: automated tests that run without any external dependency, and live integration tests that exercised real infrastructure. Both matter; neither substitutes for the other. Automated tests prove the logic is correct in isolation and stays correct as the code changes; live tests prove the real integrations (Gmail, Supabase, Claude) actually work together, which no amount of mocking can prove on its own.

## 2. Automated Validation — 242/242 Passing

Every test module runs dependency-free (no live network/DB call), invoked as `python -m tests.<module>` from `backend/`:

| Module | Checks | Covers |
|---|---|---|
| `test_agent_service` | 72 | AI Agent orchestration, intent/handling classification, guardrail scenarios (allergy, religious, discount, refund, complaint, legal, privacy, prompt injection), order-vs-RAG authority, conversation context, no-fake-callback/fallback wording |
| `test_chat_route` | 3 | Chat route: customer identification/creation, server-derived order context (ignores any client-supplied order id), blank-question rejection |
| `test_communication_adapters` | 26 | Gmail/WhatsApp adapter contracts, unconfigured-adapter fallback behavior |
| `test_notification_service` | 32 | State machine transition guards, idempotency (duplicate prevention), template rendering incl. conditional pickup-date inclusion |
| `test_inbound_service` | 21 | Inbound message deduplication, customer/order matching, conversation-history scoping |
| `test_whatsapp_inbound` | 15 | Webhook signature verification, payload parsing |
| `test_gmail_inbound` | 11 | Email parsing, threading |
| `test_customer_service` | 11 | Customer search/matching |
| `test_order_service_admin` | 11 | Order status validation, open-order matching (single/ambiguous/none) |
| `test_orders_route` | 5 | Order-creation route: triggers the "order received" draft and never blocks order creation if that draft fails, routes a non-blank note through the existing inbound pipeline without blocking creation if that fails either |
| `test_rag_service` | 9 | Embedding padding/consistency, zero-vector short-circuit, grounded-answer orchestration |
| `test_security_dependencies` | 7 | Role-based route protection |
| `test_briefing_service` | 7 | Operational briefing synthesis |
| `test_forecast_service` | 12 | ML demand forecasting |
| **Total** | **242** | |

## 3. Live Integration Validation

Not automated (by design — these exercise real external services and real credentials, deliberately outside the fast/dependency-free test suite):

- Gmail IMAP authentication against the real production account.
- Gmail SMTP authentication against the real production account.
- A real inbound email, detected by the real IMAP poller.
- A real customer identified from that email's sender address.
- Real RAG retrieval against the live knowledge base.
- A real Claude call producing a grounded draft.
- A real submit → admin-approve → send, through the real state machine.
- A real SMTP delivery, with the recipient personally confirming receipt (correct sender, subject, and body).
- A live browser smoke-check of the real deployed frontend (homepage, templates, designer, admin login) — zero console errors, real content rendered.
- Both Railway services (`web`, `cakecraft-studio`) confirmed online; Supabase connectivity confirmed via live queries.

## 4. Known Non-Blocking Limitations

Presented honestly, as limitations and future-improvement candidates — not as failures:

- **WhatsApp live delivery was not demonstrated**, because real Meta Business API credentials were not configured for this project. The adapter code, signature verification, and full pipeline integration are implemented and unit-tested; only the external credential provisioning step is outstanding.
- **Notification idempotency is enforced at the application level**, not by a database uniqueness constraint. This is an intentional choice for this academic project's scale (a single-admin-operator system, not a high-concurrency production service) — a genuine race between two simultaneous requests remains theoretically possible. A `unique` constraint on `notifications(order_id, event)` was identified as the stronger alternative and would be a small, additive migration if ever needed.
- **Failed-send error messages are not currently persisted** on the notification record itself — a `failed` status is visible to staff, but the specific delivery error is only in server logs, not the UI. Identified as an optional future improvement.
- **RAG retrieval is not perfect.** A real, observed case is documented in `docs/AI_RAG_AND_SAFETY.md` §24: a birthday-cake recommendation question did not retrieve the most relevant knowledge document. The system's safety behavior in that case was correct (it escalated rather than guessed), but this is disclosed as a genuine retrieval-quality limitation of the TF-IDF approach, not claimed away.

## 5. What Was Deliberately Not Re-Tested

Per the project's own safety rules during later development/documentation phases: no second real email was sent once the first live round trip had already proven the mechanism works — later validation reused that evidence rather than repeating a live send merely for demonstration purposes.
