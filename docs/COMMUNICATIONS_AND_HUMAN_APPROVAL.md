# Communications & Human Approval Architecture

**Status: CURRENT / AUTHORITATIVE.**

## 1. Notification Architecture

Every outbound customer communication — whether triggered automatically by an order-status change or drafted by the AI Agent in reply to an inbound message — is one row in a single `notifications` table, going through one shared state machine, reviewed in one shared admin screen (the Communications Workspace). There is no separate mechanism for "automated" vs. "AI" messages; they differ only in how the row's content was produced.

## 2. Notification Lifecycle (State Machine)

```text
queued → draft → awaiting_approval → approved → sent
                       ▲    ▲            │
                       │    └────────────┘
                       │  (return_to_draft, from awaiting_approval,
                       │   approved, or failed)
                       │
              approved → failed
```

- **`queued`**: momentarily, right after creation, before its content is rendered.
- **`draft`**: rendered content exists (template-filled or AI-drafted); editable by staff.
- **`awaiting_approval`**: submitted by any authenticated staff member.
- **`approved`**: approved by an `admin`-role staff member specifically.
- **`sent`**: delivered through the resolved channel adapter.
- **`failed`**: a configured adapter's real delivery attempt failed (not the same as "no adapter configured" — see §13).
- **`return_to_draft`**: available from `awaiting_approval`, `approved`, or `failed` — a human can always pull a message back for more work or to fix and retry a failed send.

## 3. Channels

`email` and `whatsapp` are both modeled identically at the notification-record level (a `channel` column, `email`/`whatsapp` values). The channel is set at creation — from the inbound message's own channel for AI replies, hardcoded to `email` for automated order-status drafts, or staff-chosen for on-demand drafts — and is never chosen or influenced by Claude.

## 4. Gmail

Real, implemented, **live-verified end-to-end** (see §12). Inbound: IMAP polling of `mybestcake2002@gmail.com` (a background task on the backend service, plus an on-demand "check now" admin action). Outbound: SMTP via the same account, using a Gmail App Password (never in source, never logged, never returned by any API — see `docs/FINAL_ARCHITECTURE.md` §19).

## 5. WhatsApp

Implemented — real HMAC-SHA256 signature verification on Meta's webhook, real Meta Cloud API outbound adapter — but not live-demonstrated in this project, because live delivery requires real Meta Business API credentials that were not provisioned. **Known limitation, not a defect**: even with credentials, Meta requires a pre-approved message *template* for any business-initiated message sent outside a 24-hour customer-service window; this adapter currently sends free-form text, which works for replying to a customer within that window but would be rejected by Meta for a proactive, automated status push outside it. Documented here rather than worked around, since fixing it requires an external, manual Meta template-registration step, not a code change.

## 6. Automated Order-Status Drafts

See `docs/ORDER_JOURNEY_AND_DEMO.md` for the full event list. In one sentence: a status change (or order creation) fires a deterministic, pre-written template render — not an AI generation — and still lands at `draft`, still requires the full approval chain.

## 7. AI-Generated Drafts

Produced by `agent_service.draft_reply_to_inbound_message()` — see `docs/AI_RAG_AND_SAFETY.md` for the full grounding and safety design. Also lands at `draft`, through the identical state machine.

## 8. Communications Workspace

The admin screen (`admin-notifications.html`) staff use to review everything above. A filterable, paginated list (by review-needed status, channel, and source — automated vs. AI-drafted) plus a detail drawer per notification showing: customer, order context, event, created time, current status, channel, provider message ID (once sent), and — for AI-drafted items specifically — intent, handling tier, a "human review required" callout with the reason when applicable, the original customer message, and which knowledge documents (by title only — never raw embeddings, similarity scores, or internal IDs) grounded the draft.

## 9. Customer Timeline

A per-customer, chronological merge of order-placement events, audited status changes, and every notification (at whatever stage), reachable from the Customer Detail screen — one place to see a customer's whole relationship with the business, not three disconnected views.

## 10. Review Workflow

Staff open a notification from the list, read its content and (for AI drafts) the grounding context, optionally edit the subject/body while it's still `draft`, then act.

## 11. Approval Workflow

`submit_for_approval()`: any authenticated staff member, `draft → awaiting_approval`. `approve()`: **`admin`-role staff only**, enforced at the route layer (`require_role("admin")`), `awaiting_approval → approved`. This is the one action in the whole workflow with an elevated permission requirement.

## 12. Send Workflow — Real Gmail Verification

`send()` requires `status == "approved"` — it raises otherwise. A real end-to-end round trip was completed and is the strongest evidence in this project that the architecture works, not just compiles:

```text
INBOUND:  real customer email → IMAP detection → customer identified (by email) →
          order matched (ambiguous — this customer had multiple open orders,
          correctly not guessed) → RAG retrieval → Claude draft →
          notification created at status=draft

APPROVAL: draft → submit_for_approval() → awaiting_approval →
          approve() → approved

OUTBOUND: approved → send() → GmailAdapter → real SMTP to smtp.gmail.com:587 →
          From: mybestcake2002@gmail.com → status=sent, real provider_message_id
```

The recipient personally confirmed receiving the email, with the correct subject and body. No step in this chain was mocked, stubbed, or simulated.

## 13. Failure Handling

If a channel adapter is configured but a real send attempt fails (bad credentials, provider error, no recipient address), `send()` transitions the notification to `failed`, distinct from a genuinely delivered `sent`. If no adapter is configured *at all* for a channel (or one is registered but reports itself unconfigured), the system falls back to a Sprint-1-era stub that reports success without actually delivering anything — a deliberate design choice so the rest of the pipeline (queue, drafting, approval) behaves identically whether or not real credentials happen to be present in a given environment, but a known limitation worth stating plainly: **in that fallback case, `status=sent` does not by itself prove real delivery occurred** — it proves the adapter was either absent or unconfigured. For CakeCraft's Gmail channel specifically, real credentials are configured in production and delivery was independently proven (§12).

## 14. Idempotency

Order-status-driven drafts are checked before creation: `(order_id, event)` is looked up in `notifications`, and if a row already exists for that exact pair, the existing row is returned instead of a duplicate being inserted. This is an application-level check (no new database constraint), matching the existing pattern already used for inbound-message deduplication elsewhere in the system, and is judged sufficient at this project's scale — see `docs/ORDER_JOURNEY_AND_DEMO.md` and `docs/TESTING_AND_VALIDATION.md` for the stronger, optional DB-constraint alternative that was considered but not implemented.

## 15. Auditability

Every order-status change is recorded in `audit_log` (actor, before/after status, timestamp) independently of the notification it triggers, and every notification carries its own `created_at`/`sent_at`. Combined with the Customer Timeline, a reviewer can reconstruct exactly what happened to an order and what was communicated about it, in order.

## 16. Security Boundaries

- No notification can reach `sent` without first reaching `approved`, and no code path outside `send()` (called only from the one admin route) can set `status="sent"`.
- Only `admin`-role staff can approve.
- The AI Agent module contains no call to `send()` or to any Communication Adapter, anywhere.
- Secrets are never included in a notification record, an API response, or a log message at `info` level (delivery errors are logged server-side at `exception`/`error` level, without the credential itself).
