# Milestone 09 – Order Review

**Status:** Planning

---

## Purpose

The purpose of this milestone is to introduce the first step of the checkout flow.

After completing the cake design, the customer should be able to review the complete order before providing personal information or submitting the order.

This page serves as a confidence checkpoint, allowing the customer to verify all selections and pricing before proceeding to checkout.

No business logic should be duplicated. The page must reuse the existing Designer utility modules wherever possible.

---

## Customer Journey

1. The customer completes the cake design on the Designer page.

2. The customer clicks **Continue**.

3. The Order Review page opens.

4. The customer reviews:

   - Cake image
   - Cake name
   - Cake size
   - Flavor
   - Filling
   - Frosting
   - Serving range
   - Final price

5. The customer can either:

   - Return to the Designer to make changes.
   - Continue to Customer Information.

No order is submitted during this milestone.
No customer information is collected during this milestone.

---

## User Experience Objectives

The Order Review page should provide a calm, premium, and trustworthy experience.

The page is intended for verification rather than editing.

The customer's attention should focus on confirming the order before proceeding to checkout.

Primary action:

- Continue to Customer Information

Secondary action:

- Return to Designer

The page should minimize distractions and clearly communicate the complete order without overwhelming the customer.

---

## Scope

### Included

- Display the complete cake configuration.
- Display the selected cake image.
- Display the current price.
- Display the serving range.
- Allow the customer to return to the Designer.
- Allow the customer to continue to Customer Information.

### Not Included

- Editing cake options directly on this page.
- Customer information.
- Payment.
- Order submission.
- Order persistence.
- Confirmation emails.

---

## Architecture Constraints

### Backend

No backend changes.

### Database

No database changes.

### API

No API changes.

### Frontend

The page must reuse existing utility modules wherever possible.

Business logic must not be duplicated.

The Order Review page is responsible only for presenting existing information.

Business calculations remain inside their existing modules.

### Existing Modules to Reuse

- pricing.js
- summary.js
- validation.js

### Files That May Change

- frontend/order-review.html
- frontend/js/order-review.js
- frontend/js/navigation.js (if needed)

### Files That Must Not Change

- pricing.js
- summary.js
- validation.js

unless a critical bug is discovered.

---

## Acceptance Criteria

The milestone is complete when all of the following are true:

### Functional

- The customer can navigate from the Designer page to the Order Review page.
- The complete cake configuration is displayed correctly.
- The selected cake image is displayed.
- The current price is displayed.
- The serving range is displayed.
- The customer can return to the Designer.
- The customer can continue to the Customer Information page.

### Architectural

- Existing utility modules are reused.
- No business logic is duplicated.
- No backend changes were required.
- No database changes were required.
- No API changes were required.

### Quality

- The feature works in a real browser.
- Browser Console contains no JavaScript errors.
- Existing Designer functionality continues to work.
- The implementation follows the Architecture Handbook.



