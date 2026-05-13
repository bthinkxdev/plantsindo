# Models & Payments (current behavior)

This document describes the **current (as-is)** data models and the **current payment alignment logic** in this codebase.

---

## Core models (order + payment)

All models are in `app/models/` (split across multiple files).

### `Address` (`app/models/order.py`)

- **Purpose**: Shipping/customer address.
- **Key fields**
  - `user` (optional FK): saved addresses for logged-in users.
  - `full_name`, `phone`, `email`, `address_line`, `city`, `state`, `pincode`
  - `is_default`: default saved address for the user.
  - `is_snapshot`: used to distinguish address snapshots saved with orders.

### `Order` (`app/models/order.py`)

- **Purpose**: A placed order with totals and a shipping address.
- **Key fields**
  - `user` (optional FK): null for guest checkout.
  - `order_number` (unique): human-friendly identifier used in URLs.
  - `status`: lifecycle state
    - `placed` → `confirmed` → `shipped` → `delivered`
    - `cancelled` (terminal)
  - Totals: `subtotal`, `shipping`, `gst_total`, `cgst`, `sgst`, `igst`, `total`
  - `address` (FK): address used for this order (protected from deletion).

### `OrderItem` (`app/models/order.py`)

- **Purpose**: Individual line items in an order.
- **Key fields**
  - `order` (FK)
  - **Product vs Combo** (mutually exclusive by DB constraint)
    - `product` (FK) + optional `selected_variant` (FK)
    - OR `combo` (FK)
  - Snapshots for invoices/history:
    - `product_name`, `variant_snapshot`, `unit_price`, `quantity`
  - `line_type`: `purchase` or `rental` (rental fields exist; flow depends on services).
  - GST line fields: `hsn_code`, `gst_percentage`, `taxable_value`, `gst_amount`

### `Payment` (`app/models/order.py`)

- **Purpose**: One-to-one payment record per order.
- **Key fields**
  - `order` (OneToOne)
  - `method`: `cod`, `whatsapp`, `razorpay`
  - `status`: `pending`, `paid`, `failed`
  - `amount`
  - Razorpay identifiers: `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`
  - `processed_at`

### `Shipment` (`app/models/order.py`)

- **Purpose**: Optional shipping integration state (Shiprocket).
- **Key fields**: `awb_code`, `shiprocket_*`, `current_status`, `tracking_data`, cancellation flags, `error_log`.
- **Auto behavior**: when an `Order` becomes `confirmed`, a `Shipment` can be auto-created (if delivery integration is enabled).

---

## Payment flow (Razorpay) and how it “aligns” today

This section documents how **payment status** and **order status** are kept in sync.

### 1) Checkout UI triggers Razorpay order creation

- **Page**: `templates/pages/checkout.html`
- **Frontend JS**: `static/js/checkout.js`
- When the user selects **Online Payment** (`payment_method=razorpay`) and submits the form:
  - JS prevents the normal form submit.
  - JS posts the checkout form data to:
    - `POST /checkout/create-razorpay-order/` (`store:create_razorpay_order`)

### 2) Server creates the `Order` + `Payment` (still pending)

- **View**: `CreateRazorpayOrderView` in `app/views.py`
- **What it does**
  - Validates the checkout form server-side.
  - Re-checks stock inside a DB transaction.
  - Creates an `Order` (does **not** clear the cart yet).
  - Uses Razorpay API to create a Razorpay order for `totals.total * 100` (paise).
  - Saves `payment.razorpay_order_id`.
  - Returns payload for Razorpay checkout popup:
    - `razorpay_order_id`, `razorpay_key_id`, `amount`, `order_number`, customer prefill, and `success_url`.

**Alignment at this point**

- `Order.status` stays **`placed`**
- `Payment.status` stays **`pending`**

### 3) Frontend opens Razorpay popup and verifies payment

- Razorpay popup calls the JS handler with:
  - `razorpay_payment_id`, `razorpay_signature`
- JS posts these to:
  - `POST /payment/razorpay/verify/` (`store:razorpay_verify`)

### 4) Verification aligns `Payment` + `Order` (paid → confirmed)

- **View**: `RazorpayPaymentVerifyView` in `app/views.py`
- **How it verifies**
  - Looks up `Payment` by `razorpay_order_id`
  - Recomputes signature using:
    - `HMAC_SHA256(secret, f"{order_id}|{payment_id}")`
  - Compares with `razorpay_signature`

**On success (signature matches)**

- Updates `Payment`:
  - `status = paid`
  - saves `razorpay_payment_id`, `razorpay_signature`
  - sets `processed_at = now`
- Updates `Order`:
  - `status = confirmed`
- Stock is decremented:
  - Variant stock for variant items
  - Product base stock for simple products
  - Component stock for “combo products” and “bundle combos”
- Cart is cleared and marked ordered.
- Order confirmation email is sent (best-effort).

**On failure (signature mismatch)**

- Updates `Payment.status = failed`
- Deletes the `Order` entirely
- Clears `pending_checkout_data` from session
- Returns redirect back to cart/home

### 5) Cancel flow (popup dismiss) deletes the pending order

- **Endpoint**: `POST /payment/razorpay/cancel/` (`store:razorpay_cancel`)
- **View**: `RazorpayPaymentCancelView` in `app/views.py`
- **Behavior**
  - Deletes the order (and its 1-1 payment) for the provided `order_number`
  - Redirects back to cart/home

---

## Shiprocket status alignment (delivery → order status)

Shiprocket can update shipment tracking via webhook:

- **Endpoint**: `POST /webhooks/shiprocket/` (`store:shiprocket_webhook`)
- **View**: `ShiprocketWebhookView` in `app/webhook_views.py`

**Alignment rules (current)**

- When webhook status contains `"delivered"` (case-insensitive):
  - `Order.status = delivered`
- When status contains `"rto"` or `"return"`, or `"cancelled"`:
  - `Order.status = cancelled` (unless already delivered)

---

## “Vendor” bank details (current state)

I did **not** find any `Vendor` model or any bank/payout fields in the current app code (no references to bank account / IFSC / SWIFT / IBAN, etc.). That means:

- **Current behavior**: There is **no vendor onboarding** and **no UI/API** for vendors to add bank details in this repository today.

### Recommended implementation (if you want vendors to add bank details)

If your product roadmap includes vendor payouts, the typical Django approach is:

1. **Create a model** (example: `VendorBankAccount`) linked to a “vendor” identity:
   - Either a dedicated `Vendor` model with a `OneToOne` to `AUTH_USER_MODEL`
   - Or a `UserProfile` with vendor flags + bank fields
2. **Add a form + view** in a vendor dashboard route (or reuse Django admin if only staff manage it).
3. **Restrict access** so only the vendor (or staff) can edit those details.
4. **Store only what you need**, and treat it as sensitive data (mask in UI, audit changes).

If you want, I can implement this in the codebase (model + migrations + dashboard page + validation) once you confirm the exact bank fields you need (India-only: Account No + IFSC + holder name + bank name + branch; or international: IBAN/SWIFT).

