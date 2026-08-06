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

## Handling Delays
If production falls behind schedule on a given day, the head baker should re-prioritize using the same order above, and proactively contact any customer whose pickup time is now at risk — silence is worse than an early heads-up.

## Batch Efficiency
Grouping same-flavor bakes together (all Chocolate sponges in one oven run, for example) reduces changeover time and is the standard practice on high-volume days.
