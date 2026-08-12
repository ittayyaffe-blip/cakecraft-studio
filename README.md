# CakeCraft Studio

## 1. What This Is

CakeCraft Studio ("Maison de Gâteau Paris") is a custom-cake ordering platform built as a final-degree academic project. It demonstrates a layered web application with a real external communication integration (Gmail), an AI/RAG-assisted customer communication layer, and a human-in-the-loop safety architecture in which AI can draft customer communication but can never send it unsupervised.

## 2. Academic / Demo Disclaimer

This is a demonstration system for a degree project, not a commercial product. It does not process real payments; its customer data is synthetic demo data except where explicitly noted as a real, controlled live test. See [`docs/TESTING_AND_VALIDATION.md`](docs/TESTING_AND_VALIDATION.md) for exactly what was validated with real infrastructure.

## 3. Key Capabilities

- Customer-facing cake design and ordering flow.
- Admin backoffice: order management, customer CRM, a Communications Workspace.
- Automated, deterministic customer communication drafts at every order-status transition, each individually idempotent.
- Real inbound/outbound Gmail integration (IMAP + SMTP), live-verified end-to-end.
- WhatsApp adapter infrastructure implemented and unit-tested; live delivery was not part of the final demonstration (see §13).
- An AI Agent (Claude) that drafts customer replies grounded in a RAG knowledge base and real order/customer data — never from its own general knowledge.
- A human-in-the-loop approval workflow: every communication, AI-drafted or automated, requires explicit staff approval before it can be sent.

## 4. Architecture Summary

Frontend (static HTML/CSS/JS) → FastAPI backend → a service layer (orders, customers, notifications, the AI Agent, RAG, communication adapters) → Supabase (Postgres + Auth + pgvector). Full detail in [`docs/FINAL_ARCHITECTURE.md`](docs/FINAL_ARCHITECTURE.md).

## 5. AI / RAG Safety Approach

Claude drafts language and classifies intent; it does not decide whether a communication is safe to send. The application owns a fixed risk classification per intent that can only ever be escalated by the model's own signals, never downgraded — and the application, not the model, controls the communication channel and whether anything is ever sent. Full detail, including an honestly-documented RAG retrieval limitation, in [`docs/AI_RAG_AND_SAFETY.md`](docs/AI_RAG_AND_SAFETY.md).

## 6. Human Approval Workflow

```text
draft → awaiting_approval → approved → sent
```
Every notification — automated order-status update or AI-drafted reply — starts as a draft and requires an `admin`-role staff member's explicit approval before a real send can occur. There is no automatic send path. Full detail in [`docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md`](docs/COMMUNICATIONS_AND_HUMAN_APPROVAL.md).

## 7. Technology Stack

Python (FastAPI) · HTML/CSS/vanilla JavaScript · Supabase (Postgres, Auth, pgvector) · Anthropic Claude · Gmail (IMAP/SMTP) · WhatsApp Business Cloud API (Meta) · Railway (hosting).

## 8. Deployment Overview

Two Railway services: `web` (FastAPI backend) and `cakecraft-studio` (static frontend), both backed by a shared Supabase project. See [`docs/FINAL_ARCHITECTURE.md`](docs/FINAL_ARCHITECTURE.md) §17.

## 9. Testing Status

**242/242 automated backend tests passing**, plus a real, live-verified Gmail end-to-end round trip (inbound detection → AI draft → human approval → real SMTP delivery → recipient confirmation). Full breakdown in [`docs/TESTING_AND_VALIDATION.md`](docs/TESTING_AND_VALIDATION.md).

## 10. Documentation

See [`docs/README.md`](docs/README.md) for the full documentation index, separating current/authoritative documents from the historical sprint-by-sprint development record.

## 11. Demo Flow

Customer designs and submits a cake order → admin confirms and moves it through production → each transition produces a reviewable communication draft → Communications Workspace shows both automated and AI-generated drafts, with full grounding/handling detail → staff approve and (already proven live, not repeated in every demo) send. Full script in [`docs/ORDER_JOURNEY_AND_DEMO.md`](docs/ORDER_JOURNEY_AND_DEMO.md).

## 12. Known Limitations

- WhatsApp live delivery requires Meta credentials not provisioned for this project; the adapter itself is implemented and tested.
- Notification idempotency is application-level, not a database constraint — a deliberate choice at this project's scale.
- RAG retrieval is not always perfect; the system is designed to escalate to a human rather than guess when it isn't. See [`docs/AI_RAG_AND_SAFETY.md`](docs/AI_RAG_AND_SAFETY.md) for a real, observed example.

Full detail on all limitations: [`docs/TESTING_AND_VALIDATION.md`](docs/TESTING_AND_VALIDATION.md) §4.
