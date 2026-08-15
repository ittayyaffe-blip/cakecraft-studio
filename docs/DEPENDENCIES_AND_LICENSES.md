# Dependencies & Licenses

**Status: CURRENT / AUTHORITATIVE.** Reflects the dependency/license audit performed during the Final Security & License Audit and Final Security Hardening Pass.

## Academic-Project Context

CakeCraft Studio is a final-degree university project, not a commercial product. This document exists to record what was actually checked, not to serve as a formal legal opinion. Based on dependency metadata inspected during the final project audit, no license concern requiring special distribution handling was found in the current dependency tree — see the audit method and findings below.

## 1. CakeCraft Studio's Own License

The project itself is distributed under the **MIT License** (see [`LICENSE`](../LICENSE) at the repository root).

## 2. Audit Method

License metadata was read directly from each installed package (`pip show`/npm `package.json`), not inferred or assumed. Every installed package in both the backend virtual environment (81 packages) and the frontend's one runtime npm dependency's tree (77 packages, see §4) was scanned in bulk for GPL/AGPL/LGPL/SSPL/proprietary/unlicensed markers — zero flags in either tree.

## 3. Main Direct Backend Dependencies

| Package | Purpose | License |
|---|---|---|
| `fastapi` | Web framework | MIT |
| `uvicorn` | ASGI server | BSD-3-Clause |
| `starlette` | FastAPI's foundation | BSD-3-Clause |
| `pydantic` | Data validation | MIT |
| `anthropic` | Claude API client | MIT |
| `supabase` (+ `postgrest`, `storage3`, `realtime`, `supabase-auth`, `supabase-functions`) | Postgres/Auth client | MIT |
| `httpx` | HTTP client (all outbound integrations) | BSD-3-Clause |
| `numpy` | Numerical computing (RAG embeddings, forecasting) | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| `pandas` | Data handling (ML forecasting) | BSD-3-Clause |
| `scikit-learn` | ML models (RAG TF-IDF, Random Forest forecast) | BSD-3-Clause |
| `joblib` | Model/vectorizer persistence | BSD-3-Clause |
| `python-dotenv` | Local `.env` loading | BSD-3-Clause |
| `PyJWT` | JWT handling | MIT |
| `twilio` | WhatsApp Sandbox signature verification | MIT |
| `python-multipart` | Form parsing (Twilio webhook) | Apache-2.0 |
| `cryptography` | Cryptographic primitives (transitive) | Apache-2.0 OR BSD-3-Clause |
| `requests` | HTTP client (transitive) | Apache-2.0 |

`backend/requirements.txt` pins the full resolved dependency set (81 packages total, including transitive dependencies); the table above lists only what the application code directly imports.

## 4. Main Frontend/Runtime Dependency

The frontend is static HTML/CSS/vanilla JavaScript — no build step, no framework, no bundled third-party JS/CSS libraries. The **one** real npm-managed runtime dependency is:

| Package | Purpose | License |
|---|---|---|
| `serve` | Static file server — Railway's start command for the `cakecraft-studio` frontend service | MIT |

(`serve`'s own dependency tree — 77 packages — was scanned the same way as the backend; zero flags.)

## 5. Major License Types Present

- **MIT** — permissive, requires only preserving the copyright/license notice. The large majority of both dependency trees.
- **BSD-3-Clause** — permissive, similar obligations to MIT plus a non-endorsement clause.
- **Apache-2.0** — permissive, includes an explicit patent grant.
- No dependency in either tree carries a reciprocal/copyleft license (GPL, AGPL, LGPL, SSPL) or a non-commercial/source-available license.

## 6. Fonts

Google Fonts, loaded from Google's own CDN (`fonts.googleapis.com`/`fonts.gstatic.com`), not bundled in this repository:

- **Playfair Display**
- **Inter**

Both are distributed under the SIL Open Font License, Google's standard licensing for its font catalog — no attribution file is required in the served application.

## 7. Statement

Based on the dependency and license metadata inspected during the final project audit (backend: 81 installed packages; frontend: 77 installed packages, `serve`'s tree; plus a manual review of the direct dependencies listed above), **no known reciprocal/copyleft dependency requiring special distribution handling was found in the current dependency tree.** This is a factual summary of what was checked, not a formal legal certification.

## 8. Dependency Vulnerability Status (at time of writing)

`pip-audit` against `backend/requirements.txt`: **0 known vulnerabilities.** `npm audit` against the frontend's `serve` dependency tree: **0 vulnerabilities.** See `docs/TESTING_AND_VALIDATION.md` for detail and history (two low-relevance CVEs in transitive dependencies, `cryptography` and `h2`, were found and resolved by upgrading to their patched versions during the Final Security Hardening Pass).

## 9. Audit Date

2026-08-15, during the Final Security & License Audit and the subsequent Final Security Hardening Pass.
