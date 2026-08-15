# Communications & Human Approval Architecture

**Status: CURRENT / AUTHORITATIVE.**

## 1. Notification Architecture

Every outbound customer communication — whether triggered automatically by an order-status change or drafted by the AI Agent in reply to an inbound message — is one row in a single `notifications` table, going through one shared state machine, reviewed in one shared admin screen (the Communications Workspace). There is no separate mechanism for "automated" vs. "AI" messages; they differ only in how the row's content was produced.

## 2. Notification Lifecycle (State Machine) — Current, Simplified Workflow

```text
queued → draft → sent
              └→ failed → (retry, i.e. Send again) → sent
```

- **`queued`**: momentarily, right after creation, before its content is rendered.
- **`draft`**: rendered content exists (template-filled or AI-drafted); editable by staff.
- **`sent`**: delivered through the resolved channel adapter, by any authenticated staff member clicking **Send** — no separate approval role required.
- **`failed`**: a configured adapter's real delivery attempt failed (not the same as "no adapter configured" — see §13). A failed notification's Send button becomes "Retry Send," which is simply calling Send again.

This is a deliberate simplification from an earlier design: the notification model and backend routes still technically retain `awaiting_approval`/`approved` as valid statuses and `submit_for_approval()`/`approve()` (`admin`-role-only) functions and routes, but **the current frontend (`admin-notifications.js`) only ever calls Send** — the current, real, day-to-day workflow is `draft → Send → sent/failed`, one click, by any authenticated staff member. The one safety property the old two-step design existed for is unchanged and still absolute: a draft is *never* sent automatically, and every send still goes through this same one function.

## 3. Channels

`email` and `whatsapp` are both modeled identically at the notification-record level (a `channel` column, `email`/`whatsapp` values, plus `chat` for live Chat Q&A answers that reached the customer directly — see `docs/AI_RAG_AND_SAFETY.md` §11). The channel is set at creation — from the inbound message's own channel for AI replies, resolved automatically for order-status drafts (WhatsApp if the customer has an existing WhatsApp thread, otherwise email — see §6), or staff-chosen for on-demand AI Agent drafts — and is never chosen or influenced by Claude.

## 4. Email

Real, implemented, **live-verified end-to-end** (see §12). **Inbound**: IMAP polling of `mybestcake2002@gmail.com` — a background `asyncio` task started in the FastAPI app's own lifespan on every deploy, plus an on-demand "check now" admin action. **Outbound**: **Resend's HTTPS API**, not SMTP — Railway blocks outbound SMTP at the network level (confirmed by direct in-container testing), so a raw SMTP send could never have worked from this host. Resend sends from its own shared sandbox address with `Reply-To` set to the real business address so customer replies land correctly. The Gmail App Password is still used, but only for IMAP inbound and the Reply-To header — never for sending. All credentials live only in Railway environment variables (see `docs/FINAL_ARCHITECTURE.md` §24).

## 5. WhatsApp

**The live, currently-configured WhatsApp integration is the Twilio WhatsApp Sandbox** — not the Meta Cloud API (a separate, independently complete Meta adapter also exists in the codebase and is unit-tested, but is not the one selected in production; see `docs/FINAL_ARCHITECTURE.md` §13).

Honest current status:

- **Outbound adapter: implemented and verified.** Real HTTP calls to Twilio's Messages API succeed, with the correct Sandbox "From" number and correct credentials — confirmed directly against Twilio's own Message-status API.
- **Inbound webhook: implemented and deployed.** `POST /webhooks/twilio-whatsapp` is live, publicly reachable, verifies Twilio's `X-Twilio-Signature` before trusting anything, and correctly parses Twilio's real payload shape (`From`/`To`/`Body`/`MessageSid`).
- **A real customer WhatsApp message reaching Twilio was manually verified** — confirmed directly in Twilio's own message log (`status: received`, a real Message SID, timestamp, and body).
- **CakeCraft's own inbound routing (Twilio → our webhook → `inbound_messages` → Communications Inbox) has NOT passed end-to-end**, and this document does not claim otherwise. Root cause, diagnosed via Twilio's own account API and Railway's HTTP logs: Twilio's Sandbox "When a message comes in" webhook URL is currently unset — confirmed both by the complete absence of any request to our webhook route in Railway's logs, and by Twilio's own literal fallback reply to the customer ("...Configure your WhatsApp Sandbox's Inbound URL to change this message"), which Twilio only sends when that field is blank. Twilio provides no REST API to read or set this field for this account/product (verified directly — every plausible endpoint returns 404); it is a one-time, Console-only manual action. **This is a demo/Sandbox limitation, not a production WhatsApp claim, and not an application defect** — the webhook code itself is correct and ready.
- **Outbound free-form/24-hour-window limitation** (separate from the above): the adapter always sends free-form `Body` text — there is no Message Template support in this codebase — so a proactive/automated message to a customer with no recently-open 24-hour session is rejected by WhatsApp (`error 63016`), observed live and documented rather than hidden.

## 6. Automated Order-Status Drafts

See `docs/ORDER_JOURNEY_AND_DEMO.md` for the full event list and lifecycle detail. In one sentence: a customer-relevant order-status change fires a deterministic, pre-written template render — not an AI generation — and still lands at `draft`, still requires a human's explicit Send click. Covers `confirmed`, `in_progress`, `ready`, `completed`, and `cancelled` (a `pending`/"order received" draft also fires at order creation). The draft's channel is resolved automatically (WhatsApp if the customer has an existing WhatsApp thread with the bakery, otherwise email) rather than defaulting blindly to one channel. In the Admin Orders drawer, the moment staff confirms a status change, the drawer shows a direct "Customer update draft created — Review in Communications" action, deep-linking straight to that notification (`admin-notifications.html?id=...`) — no manual searching required. Repeating the same status change never creates a duplicate draft (§14).

## 7. AI-Generated Drafts

Produced by `agent_service.draft_reply_to_inbound_message()` — see `docs/AI_RAG_AND_SAFETY.md` for the full grounding and safety design. Also lands at `draft`, through the identical, simplified state machine (§2).

## 8. Communications Workspace

The admin screen (`admin-notifications.html`) staff use to review everything above. A filterable, paginated list (by review-needed status, channel, and source — automated vs. AI-drafted) plus a detail drawer per notification showing: customer, order context, event, created time, current status, channel, provider message ID (once sent), and — for AI-drafted items specifically — intent, handling tier, a "human review required" callout with the reason when applicable, the original customer message, and which knowledge documents (by title only — never raw embeddings, similarity scores, or internal IDs) grounded the draft. Also includes a real WhatsApp conversation-thread view and a status banner honestly stating which WhatsApp provider (Twilio Sandbox / Meta / none) is currently live, so a Sandbox test session is never mistaken for a real WhatsApp Business connection.

## 9. Customer Timeline

A per-customer, chronological merge of order-placement events, audited status changes, and every notification (at whatever stage), reachable from the Customer Detail screen — one place to see a customer's whole relationship with the business, not three disconnected views.

## 10. Review Workflow

Staff open a notification from the list (or arrive via a direct deep link from the Admin Orders drawer — §6), read its content and (for AI drafts) the grounding context, optionally edit the subject/body while it's still `draft`, then click **Send**.

## 11. Send Workflow

Any authenticated staff member can send — there is currently no elevated-role requirement in the real workflow (the underlying `require_role("admin")` check still exists on the legacy, frontend-unused `/approve` route only). `send()` accepts a notification from `draft`, `failed`, or (for completeness, if ever reached via the legacy routes) `approved`.

## 12. Send Workflow — Real Email Verification

A real end-to-end round trip was completed and is the strongest evidence in this project that the architecture works, not just compiles:

```text
INBOUND:  real customer email → IMAP detection → customer identified (by email) →
          order matched (ambiguous — this customer had multiple open orders,
          correctly not guessed) → RAG retrieval → Claude draft →
          notification created at status=draft

OUTBOUND: draft → Send (one staff click) → ResendAdapter → real HTTPS delivery
          via Resend → From: Resend's shared address, Reply-To: mybestcake2002@gmail.com →
          status=sent, real provider_message_id
```

The recipient personally confirmed receiving the email, with the correct subject and body. No step in this chain was mocked, stubbed, or simulated.

## 13. Failure Handling

If a channel adapter is configured but a real send attempt fails (bad credentials, provider error, no recipient address, WhatsApp's free-form/24-hour-window rule), `send()` transitions the notification to `failed`, distinct from a genuinely delivered `sent`. If no adapter is configured *at all* for a channel (or one is registered but reports itself unconfigured), the system falls back to a stub that reports success without actually delivering anything — a deliberate design choice so the rest of the pipeline (queue, drafting, sending) behaves identically whether or not real credentials happen to be present in a given environment, but a known limitation worth stating plainly: **in that fallback case, `status=sent` does not by itself prove real delivery occurred.** For CakeCraft's Email channel specifically, real credentials are configured in production and delivery was independently proven (§12). For WhatsApp, real credentials are also configured and outbound delivery attempts are real (verified against Twilio directly — see §5), even though the specific message observed there failed for the documented free-form/window reason, not a fallback stub.

## 14. Idempotency

Order-status-driven drafts are checked before creation: `(order_id, event)` is looked up in `notifications`, and if a row already exists for that exact pair, the existing row is returned instead of a duplicate being inserted — repeating the same status transition (or re-saving the status the order is already at, which the transition-validation layer treats as a harmless no-op) never creates a second draft. This is an application-level check (no new database constraint), matching the existing pattern already used for inbound-message deduplication elsewhere in the system, and is judged sufficient at this project's scale — see `docs/ORDER_JOURNEY_AND_DEMO.md` and `docs/TESTING_AND_VALIDATION.md` for the stronger, optional DB-constraint alternative that was considered but not implemented.

## 15. Auditability

Every order-status change is recorded in `audit_log` (actor, before/after status, timestamp) independently of the notification it triggers, and every notification carries its own `created_at`/`sent_at`. Combined with the Customer Timeline, a reviewer can reconstruct exactly what happened to an order and what was communicated about it, in order.

## 16. Security Boundaries

- No notification can reach `sent` without going through `send()` — the one function called only from the one admin `/send` route — and a draft is never sent automatically by any code path, including order-status changes and AI drafting, both of which stop at `draft`.
- Sending itself requires only an authenticated staff session (`get_current_admin`), not a specific role, in the current workflow (§11); the one remaining role-gated action (`approve`, on the legacy, frontend-unused route) still requires the `admin` role.
- The AI Agent module contains no call to `send()` or to any Communication Adapter, anywhere.
- Secrets are never included in a notification record, an API response, or a log message at `info` level (delivery errors are logged server-side at `exception`/`error` level, without the credential itself).
