# AI Operations Agent / AI Knowledge Assistant — Evidence Package

**Captured:** 2026-08-09, 16:47–16:49 (local)
**Environment:** production — Backoffice at `https://cakecraft-studio-production.up.railway.app`, backend at `https://web-production-c9dd99.up.railway.app`
**Method:** headless Chrome driven over the Chrome DevTools Protocol, authenticated as the real admin account, against real production data (2,628 real seeded orders). Every question below was actually submitted through the real UI; every answer below is copied verbatim from what the production application actually returned — nothing in this document was written or edited by hand.

---

## 1. AI Knowledge Assistant (RAG)

**Question asked:** *"What is your policy on wedding cake deposits?"*

**Answer returned:**
> Wedding orders require a **non-refundable 30% deposit**, collected at design confirmation.
>
> This deposit is not covered under the standard cancellation refund policy — even if a customer cancels more than 7 days out (which would normally qualify for a full refund elsewhere), the wedding deposit itself is still forfeited.

**Sources displayed:** Pricing Policy — Maison de Gâteau Paris; Frequently Asked Questions — Maison de Gâteau Paris; Delivery Policy — Maison de Gâteau Paris; Frequently Asked Questions — Maison de Gâteau Paris; Pickup Policy — Maison de Gâteau Paris.

**Loading state:** `#ragAskResult`'s `role` attribute was confirmed `"status"` during the "Searching the knowledge base…" state and remained `"status"` after the answer rendered — the accessibility fix from an earlier session verified live again here.

**Screenshots:**
- `02_rag_knowledge_assistant_idle.png` — the panel before any question is asked.
- `03_rag_knowledge_assistant_loading.png` — the loading state ("Searching the knowledge base…"), captured alongside the rest of the dashboard's own loading states.
- `04_rag_knowledge_assistant_answer_with_sources.png` — the full answer with sources, in context on the real dashboard.

**What this proves:** the answer states a specific, correct policy fact (30% deposit, non-refundable, tied to wedding orders specifically) that only exists in the bakery's own knowledge base documents — not general knowledge about bakeries — and the sources cited are real document titles pulled from live pgvector retrieval, not static/hardcoded text.

---

## 2. AI Operations Agent — Operations Q&A

**Question asked:** *"What should I prioritize today given tomorrow's forecast?"*

**Answer returned (verbatim):**
> ## Today's Priorities
>
> **1. Clear the 5 overdue/at-risk pickups immediately** — these are today's most urgent items, since "silence is worse than an early heads-up":
>
> - **Ready for pickup now** (should already be in customers' hands — contact them today):
>   - Arthur Lefevre — Little Feet Delight
>   - Gabriel Andre — Rose Gold Number Cake
>
> - **Still in progress, pickup due/overdue today** (need to finish and/or call to reset expectations):
>   - Liam Bernard — Class of Photo Cake
>   - Yuki Boyer — Storybook Baby Cloud
>   - Wei Garcia — Chocolate Confetti Celebration
>
> For the three still "in_progress," get them finished today or proactively call each customer with a revised pickup window — don't let them find out at the counter.
>
> **2. Clear the notification backlog before end of day** — 21 pending notifications awaiting approval is a lot to carry into a Very High workload day. If any of these relate to tomorrow's 6 confirmed/forecast orders (pickup reminders, confirmations, allergen disclosures, etc.), approve/send them today so tomorrow's floor staff aren't managing both baking and a communications backlog simultaneously.
>
> **3. Prep for tomorrow now, since today has zero orders/revenue and full capacity to prep:**
> - Tomorrow is forecast Very High workload — 6 orders, $1,190.06, with 5 already confirmed and only 45% confidence

**Sources displayed:** Production Workflow — Maison de Gâteau Paris; Frequently Asked Questions — Maison de Gâteau Paris; Wedding Cake Guide — Maison de Gâteau Paris; Allergen Policy — Maison de Gâteau Paris.

**Screenshot:** `05_ai_operations_agent_answer.png` — shows the full answer alongside the AI Daily Briefing panel it draws its numbers from, on the same page, so the correspondence between the two is directly visible (5 high-priority orders in the Briefing = the 5 named orders in the Agent's answer; "6 predicted orders / Very High / 45% confidence" in the Briefing = the same numbers in the Agent's answer).

**What this proves:** the Agent's answer isn't generic advice — it names the actual overdue orders by customer and cake, cites the actual forecast numbers (6 orders, $1,190.06, Very High, 45%), and the actual pending-notification count (21), all of which are visibly identical to the real, live AI Daily Briefing panel rendered on the same page. This is the live operational + ML-forecast context genuinely reaching the model, not a canned response.

---

## 3. AI Agent Insights (morning-briefing narrative)

Captured on the same dashboard load, in `01_dashboard_daily_briefing_and_agent_insights.png` and `05_ai_operations_agent_answer.png`:

> Quiet on paper today with zero orders logged, but that's deceptive — five high-priority pickups are overdue or due today (two of them still in_progress) and need to be closed out today, and tomorrow looks like a real Saturday crunch with 6 orders and $1,190 on the books at Very High workload. Get the overdue cakes finished and out the door so tomorrow's decorator isn't starting behind.

With structured **Production** / **Staffing** / **Inventory** notes underneath, e.g. Staffing: *"Add a second decorator (or third baker) for tomorrow given the Very High workload forecast — decoration capacity is the likely constraint with 6 orders due."*

**Grounded in:** Bakery Operations Manual — Maison de Gâteau Paris; Production Workflow — Maison de Gâteau Paris (×2).

**What this proves:** this is the LLM-generated interpretive layer described in `docs/BUSINESS_INTELLIGENCE_LAYER.md`'s "Which layer is deterministic vs. LLM-generated" section — distinct from the AI Daily Briefing's own deterministic Recommended Actions (also visible in the same screenshot, directly above it, for contrast).

---

## 4. Customer Communication Draft — Human-in-the-Loop Evidence

**Real order used:** Hugo Bernard — Golden Achievement Cake — status "In Progress" — order placed Aug 7, 2026.

**Staff instruction given:** *"Give them a warm, brief update on how their order is progressing."*

**Draft generated (verbatim, subject + opening):**
> **Subject:** A Sweet Update on Your Golden Achievement Cake, Hugo!
>
> Dear Hugo, Congratulations again on the big graduation milestone! I wanted to give you a quick, warm update on your Golden Achievement Cake — it's coming along [...]

**Confirmation shown in the UI:** *"Draft created — review it in the Notification Queue."*

**Screenshots:**
- `06_ai_agent_draft_created_confirmation.png` — the order drawer immediately after the draft was created.
- `07_notification_queue_showing_draft_status.png` — the new draft (top row, timestamped 4:48 PM) now genuinely present in the real Notification Queue, filtered to `Draft` status, alongside every other real draft notification currently in the system (503 total).
- `08_notification_draft_detail_pending_human_approval.png` — **the decisive piece of evidence**: opening the new draft shows its full content and an **Actions section containing exactly one button: "Submit for Approval."** No Send, no Approve, no direct-dispatch action is reachable from this screen.

**What this proves:** Claude generated the message text, but the resulting row landed at `status: "draft"` in the same queue every staff-authored draft already uses, and the *only* action available from that state is to submit it for a second human (an admin) to separately approve, and a third step to actually send — exactly the structural, code-enforced workflow described in this project's audits. **No approval or send action was taken during this capture** — the draft remains sitting at `Draft` status in production, exactly as it should.

---

## Limitations of this evidence package

- This captures one representative question per feature, not a systematic evaluation of answer quality or retrieval accuracy across many queries.
- The RAG/Agent "not configured" fallback paths and the exception-handling paths were not captured here (they're covered by the offline mocked tests in `test_rag_service.py`/`test_agent_service.py` instead, not by live screenshots).
- One judgment call worth stating plainly: screenshots 06 and 08 show a real order's customer contact fields (email/phone) alongside the AI Agent evidence. This is synthetic, seeded demo data (`@demo.maisondegateau.test` — a domain reserved by RFC 2606 specifically so it can never resolve to a real address), not a real person's information, generated by this project's own `tools/demo_data_seed.py`.
