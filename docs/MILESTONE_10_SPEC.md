# Milestone 10 – Customer Information

## Goal

Allow the customer to enter the information required to place an order.

## Scope

### Display

- Customer Name
- Phone Number
- Email Address
- Notes (optional)

### Actions

- Back to Order Review
- Submit Order

## Validation

- Name is required.
- Phone is required.
- Email is required.
- Notes are optional.

## Architecture

Frontend:
- New page: customer-information.html
- New controller: customer-information.js

Backend:
- No changes.

Database:
- No changes.

API:
- No changes.

## Reuse

Reuse the existing Order Review flow.

Do not duplicate business logic.

## Definition of Done

- Customer can enter personal information.
- Validation works.
- Submit button becomes enabled only when required fields are valid.
- Back button returns to Order Review.
