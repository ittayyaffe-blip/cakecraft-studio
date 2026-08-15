# Production Workflow — Maison de Gâteau Paris

## Status Pipeline
Every order moves through the same six stages: **pending → confirmed → in_progress → ready → completed**, or **cancelled** at any point before completion. Production work maps onto this pipeline as follows:

- **pending** — order placed, not yet reviewed by staff. No production has started.
- **confirmed** — staff has reviewed and accepted the order; it is scheduled into the production calendar, backward from its pickup/delivery date.
- **in_progress** — active production: baking, filling, crumb-coating, and decoration, in that order (see Bakery Operations Manual for the daily rhythm this follows).
- **ready** — decoration is complete; the cake is refrigerated and staged for pickup or delivery.
- **completed** — the cake has been collected or delivered.

## Scheduling Logic
Production is scheduled backward from the pickup date, not forward from the order date. A cake's bake day is chosen so that filling/stacking, crumb-coating, and final decoration each get a full production slot before the scheduled pickup — working backward avoids the common mistake of starting too late and rushing decoration, which is where most quality issues originate.

## Priority Order Within a Day
When multiple orders are scheduled for production on the same day:
1. **Wedding orders** always take priority — the highest stakes and least schedule flexibility (see Wedding Cake Guide).
2. Orders with the **nearest pickup/delivery time** next.
3. **Large size** orders before Small/Medium of the same priority tier, since they need more time.

## Order Priority Levels
CakeCraft's ordering system calculates a priority level for every confirmed/in-progress/ready order, automatically and consistently — the same underlying facts (pickup date, pickup proximity, production status, collection) always produce the same result. This is a **decision-support signal for the manager, not an automatic authorization**: a priority level never changes an order's status, sends a customer message, or approves anything by itself — every actual production or status change still goes through the normal manual Back Office review, or a manager's explicit approval when the AI Bakery Manager proposes one.

- **CRITICAL** — pickup is today or already overdue. Needs immediate operational attention: get it into production or contact the customer without delay.
- **HIGH** — pickup is within the next 2 days, or the order is a confirmed Wedding whose production hasn't started yet (Wedding orders get zero schedule slack regardless of the exact date — see Wedding Cake Guide). Production attention should be scheduled very soon, today or tomorrow.
- **NORMAL** — a confirmed/in-progress/ready order with a real pickup date more than 2 days away. On track; normal planned production workflow, no acceleration needed.
- **LOW** — a ready order with a comfortable pickup buffer (more than 2 days out). Production is already complete; this is routine monitoring while the cake awaits customer collection.
- **NEEDS INFO** — the order is missing a pickup date. This is treated as an **exception requiring manager attention, not automatically as CRITICAL** — a missing pickup date means the true urgency genuinely isn't known yet, so the system never guesses one; a manager should follow up with the customer to get a real date. Orders not yet reviewed by staff (`pending`) or already finished (`completed`/`cancelled`) simply have no production priority — there's nothing to schedule for either case.

## Pickup Scheduling Reference
The same pickup policy the Pickup Policy and Bakery Operations Manual documents describe, restated here for priority context:
- Pickup hours are **9:00 AM–6:00 PM, Tuesday through Sunday** — the bakery is **closed Mondays**, so Monday is never an available pickup day.
- Minimum notice by collection: Birthday/Baby Shower/Graduation need 2–14 days, Corporate needs 3–10 days, Wedding needs 14–45 days (see Bakery Operations Manual).
- A customer who chooses a pickup date inside their collection's own minimum notice window is still allowed to order — the system treats it as a **rush request**: the order is accepted and flagged for manager attention on availability, never silently promised or silently blocked.

## Handling Delays
If production falls behind schedule on a given day, the head baker should re-prioritize using the same order above, and proactively contact any customer whose pickup time is now at risk — silence is worse than an early heads-up.

## Batch Efficiency
Grouping same-flavor bakes together (all Chocolate sponges in one oven run, for example) reduces changeover time and is the standard practice on high-volume days.
