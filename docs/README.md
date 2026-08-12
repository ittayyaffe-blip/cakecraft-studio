# CakeCraft Studio — Documentation Index

CakeCraft Studio is a final-degree academic project: a custom-cake ordering platform demonstrating a layered web application, a real external communication integration (Gmail), an AI/RAG-assisted customer communication layer, and a human-in-the-loop safety architecture. See the root [`README.md`](../README.md) for the project overview.

## Current / Authoritative Documentation

These five documents describe the system **as it exists in the final submission**. Read them in this order for a full picture:

| Document | Covers |
|---|---|
| [`FINAL_ARCHITECTURE.md`](FINAL_ARCHITECTURE.md) | The complete system architecture — frontend, backend, service layer, database, deployment, all integrations, security boundaries. Start here. |
| [`AI_RAG_AND_SAFETY.md`](AI_RAG_AND_SAFETY.md) | How AI and RAG are used, the exact boundary between what Claude decides and what the application decides, the dietary/allergy/religious safety policy, and an honestly-documented RAG retrieval limitation. |
| [`COMMUNICATIONS_AND_HUMAN_APPROVAL.md`](COMMUNICATIONS_AND_HUMAN_APPROVAL.md) | The notification state machine, Gmail/WhatsApp channels, the Communications Workspace, and the real Gmail end-to-end verification. |
| [`ORDER_JOURNEY_AND_DEMO.md`](ORDER_JOURNEY_AND_DEMO.md) | The order-status communication journey, idempotency design, and the recommended demonstration script. |
| [`TESTING_AND_VALIDATION.md`](TESTING_AND_VALIDATION.md) | The 242/242 automated test suite, the separate live-integration validation, and known non-blocking limitations. |

## Historical / Development Record

The documents below record the project's development history, sprint by sprint. They are preserved as-is and were **not** rewritten during final documentation consolidation — where a historical document's content has since been superseded, the current-state documents above are authoritative, not these:

- `ARCHITECTURE.md` — an early-project architecture document; superseded by `FINAL_ARCHITECTURE.md` (see the pointer note at its top).
- `Master_Blueprint_v1.md`, `Project_Audit_Report_v1.md`, `Bakery_Command_Center_UX_Product_Blueprint_v1.md`, `UI_VISION.md`
- `SPRINT1_EVENT_DRIVEN_COMMUNICATION.md`, `SPRINT2_DEMO_DATA.md`, `SPRINT3_COMMUNICATION_ADAPTER.md`, `SPRINT4_WHATSAPP_ADAPTER.md`
- `BUSINESS_INTELLIGENCE_LAYER.md`, `FINAL_AI_INTELLIGENCE_PHASE.md`
- `EPIC1_BACKOFFICE.md`, `EPIC1_CUSTOMERS.md`, `PHASE1_IDENTITY_SECURITY.md`, `MILESTONE_09_SPEC.md`, `MILESTONE_10_SPEC.md`, `RELEASE_0.2.md`, `DATASET_SCALE_UP.md`, `IMAGE_LIBRARY.md`, `PROJECT_RULES.md`
- `evaluation/`, `screenshots/`

These remain valuable as a record of *how* the system was built and the reasoning behind individual decisions along the way; they are not maintained to stay current and should not be read as describing the final system on their own.
