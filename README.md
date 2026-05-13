# Plants 99 — E‑commerce platform

Django 6 storefront and staff dashboard: catalog (simple products and multi-attribute variants), cart and checkout, Razorpay payments, optional Shiprocket shipping, GST-aware totals, and reporting.

---

## Table of contents

1. [Features](#features)
2. [Tech stack](#tech-stack)
3. [Repository layout](#repository-layout)
4. [Local development](#local-development)
5. [Environment variables](#environment-variables)
6. [URLs and entry points](#urls-and-entry-points)
7. [Data model (high level)](#data-model-high-level)
8. [Integrations](#integrations)
9. [Feature flags and business rules](#feature-flags-and-business-rules)
10. [Useful commands](#useful-commands)
11. [Static files and media](#static-files-and-media)
12. [Production notes](#production-notes)
13. [Models & payments docs](#models--payments-docs)

---

## Features

| Area | What’s included |
|------|------------------|
| **Catalog** | Categories, products with optional **variants** (attributes + values, SKU, price, stock, images per variant), or **simple** products (base price/stock + `ProductImage`) |
| **Storefront** | Home, product list/detail, cart, checkout, order success/history, static pages (about, contact, privacy, terms, shipping), newsletter subscribe |
| **Auth** | OTP-based login, account dashboard, profile, saved addresses |
| **Payments** | Razorpay order creation and payment verification |
| **Orders** | Order placement from cart, line items, GST fields on orders, flat delivery charge |
| **Admin UX** | Custom **`/dashboard/`** panel for products, orders, banners, categories, reports, reviews, messages; Django **`/admin/`** for standard model admin |
| **Optional** | Wishlist (when enabled), Shiprocket webhook and shipment helpers, AWS S3 media storage |

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Framework | **Django 6.0** |
| DB (default) | **SQLite** (`db.sqlite3`); PostgreSQL config commented in `ecom/settings.py` |
| Config | **python-decouple** (`.env`) |
| HTTP / APIs | **requests** |
| Payments | **razorpay** |
| Images | **Pillow** |
| Color utilities | **webcolors** |
| Reports export | **openpyxl** |
| Object storage | **boto3**, **django-storages** (when `USE_S3=True`) |
| Static serving | **WhiteNoise** |

---

## Repository layout

```
plants_99/
├── ecom/                 # Django project (settings, root urls, WSGI/ASGI)
├── app/                  # Main application
│   ├── models.py         # Catalog, cart, orders, addresses, reviews, etc.
│   ├── views.py          # Storefront views
│   ├── admin_views.py    # Custom dashboard views
│   ├── admin_urls.py     # /dashboard/ routes
│   ├── auth_views.py     # OTP login, account, addresses
│   ├── services/         # Cart/order, Shiprocket, parcel logic
│   ├── webhook_views.py  # Shiprocket webhook
│   └── management/commands/  # e.g. seed_jewellery, audit_variant_integrity
├── templates/            # HTML templates (store, auth, admin, emails)
├── static/               # CSS, JS, images (collect to staticfiles for prod)
├── media/                # Local uploads (when not using S3)
├── custom_storage.py     # Media storage backend hook for S3
├── s3_tagging_utils.py   # S3 object tags for uploads
├── manage.py
├── requirements.txt
└── .env                  # Local secrets (not committed)
```

---

## Local development

### Prerequisites

- Python 3.x compatible with Django 6  
- (Optional) Virtual environment

### Setup

```bash
cd zanha_jewels
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` from the template and set at least the **required** variables (see [Environment variables](#environment-variables)):

```bash
copy .env.example .env
# Edit .env
```

Apply migrations and create a superuser. Superusers have `is_staff` and can use both `/admin/` and `/dashboard/` (dashboard enforces staff in `app/admin_views.py`).

```bash
python manage.py migrate
python manage.py createsuperuser
```

Run the development server:

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`.

### Optional demo data

```bash
python manage.py seed_jewellery
```

Seeds jewellery categories and sample simple products (no variants).

---

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DJANGO_SECRET_KEY` | Yes | Django secret |
| `DJANGO_DEBUG` | Yes | `True`/`False` |
| `ALLOWED_HOSTS` | Yes (prod) | Comma-separated hosts; with `DEBUG=True`, hosts are relaxed in code |
| `EMAIL_HOST_USER` | Yes* | SMTP user |
| `EMAIL_HOST_PASSWORD` | Yes* | SMTP password |
| `RZP_CLIENT_ID` | For checkout | Razorpay key id |
| `RZP_CLIENT_SECRET` | For checkout | Razorpay key secret |
| `SHIPROCKET_EMAIL` | If using Shiprocket | API login email |
| `SHIPROCKET_PASSWORD` | If using Shiprocket | API password |
| `USE_S3` | No | `True` to store media on S3 |
| `AWS_*` | When `USE_S3=True` | Access key, secret, bucket, region (see `ecom/settings.py`) |
| `REVIEW_ENABLED` | No | Storefront product reviews |
| `DEBUG_TRACE` | No | Extra tracing for product edit flow |
| `SITE_PHONE`, `SITE_WHATSAPP`, `SITE_EMAIL`, `SITE_INSTAGRAM` | No | Defaults exist in settings |

\* Required if you rely on outgoing email (OTP, order confirmation, contact notifications).

Full template: [`.env.example`](.env.example).

---

## URLs and entry points

| URL prefix | Description |
|------------|-------------|
| `/` | Storefront (home, products, cart, checkout, orders, static pages) |
| `/accounts/` | OTP login, logout, account, profile, addresses |
| `/dashboard/` | Custom staff panel (`is_staff=True`; separate login at `/dashboard/login/`) |
| `/admin/` | Django built-in admin |

**Storefront** routes are defined in `app/urls.py` (`app_name = "store"`). Notable patterns:

- `store:home`, `store:product_list`, `store:product_detail`
- `store:cart`, `store:checkout`, `store:order_create`, Razorpay verify/cancel
- JSON/HTML APIs: new arrivals, cart drawer, wishlist toggles, variant resolve, etc.

**Webhook:** `POST /webhooks/shiprocket/` → `ShiprocketWebhookView`.

---

## Data model (high level)

- **`Category`** — product taxonomy.  
- **`Product`** — shared fields (name, slug, description, flags like featured/bestseller/deal, GST, simple `base_price` / `base_stock` when there are no variants).  
- **`ProductAttribute`** / **`ProductAttributeValue`** — e.g. Color: Gold.  
- **`Variant`** — price, original price, stock, SKU, dimensions/weight, images via **`VariantImage`**. Linked to attribute values through **`VariantAttributeValue`**.  
- **`ProductImage`** — images for **simple** products only (no variants).  
- **`Cart`** / **`CartItem`** — session or user carts; items reference product + optional variant.  
- **`Address`** — shipping addresses (can be snapshotted on orders).  
- **`Order`** / **`OrderItem`** — placed orders, totals including **`gst_total`**, CGST/SGST/IGST split fields where used.  
- Additional models (banners, reviews, newsletter, messages, etc.) live in `app/models.py`.

---

## Integrations

### Razorpay

Configured in `ecom/settings.py` as `RZP_CLIENT_ID` and `RZP_CLIENT_SECRET`. Storefront flow creates orders and verifies payments via views wired in `app/urls.py`.

### Shiprocket

Credentials in settings; services in `app/services/shiprocket_service.py`, `app/shiprocket.py`. Dashboard can retry/cancel shipments and refresh tracking. Webhook updates can be received at `/webhooks/shiprocket/`.

### Email

`EMAIL_BACKEND` points to `app.email_backend.CustomEmailBackend` with Gmail SMTP defaults. Used for OTP, order emails, and admin notifications (see `ADMIN_NOTIFICATION_EMAILS` in settings).

### AWS S3

When `USE_S3=True`, media uses `custom_storage.MediaFileStorage` with optional object tagging (`s3_tagging_utils`). Static files remain on the default static storage (local + WhiteNoise pattern).

---

## Feature flags and business rules

Defined in `ecom/settings.py` (some overlap with env):

| Setting | Meaning |
|---------|---------|
| `DELIVERY_INTEGRATED` | Delivery integration toggle |
| `WISHLIST_ENABLED` | Wishlist UI/API |
| `HOME_*_ENABLED` | Home sections (deal of day, featured, bestseller, recently added) |
| `ALLOW_ATTRIBUTES_AND_VARIANTS` | Attribute/variant merchandising |
| `REVIEW_ENABLED` | Product reviews |
| `FLAT_DELIVERY_CHARGE` | Flat shipping amount (default ₹80) |
| `MAX_CART_QTY` | Per-line quantity cap |
| `TIME_ZONE` | `Asia/Kolkata` |

Guest sessions: `EnsureGuestSessionMiddleware` ensures a session key for guest cart/wishlist.

---

## Useful commands

| Command | Purpose |
|---------|---------|
| `python manage.py migrate` | Apply DB migrations |
| `python manage.py seed_jewellery` | Demo categories + simple products |
| `python manage.py audit_variant_integrity` | Variant data checks |

---

## Static files and media

- **Development:** `STATICFILES_DIRS` includes `static/`; `MEDIA_ROOT` is `media/` when S3 is off.  
- **Production:** run `python manage.py collectstatic`; WhiteNoise serves static files from `STATIC_ROOT` (`staticfiles/`).

---

## Production notes

1. Set `DJANGO_DEBUG=False` and a strong `DJANGO_SECRET_KEY`.  
2. Set `ALLOWED_HOSTS` to real domain(s).  
3. Use HTTPS and set `SESSION_COOKIE_SECURE=True` (and CSRF cookie secure) when appropriate — currently `SESSION_COOKIE_SECURE` is `False` in settings for local HTTP; adjust for production.  
4. Configure a production database (PostgreSQL block is ready to uncomment in `ecom/settings.py`).  
5. Point `EMAIL_*` and Razorpay/Shiprocket keys to live credentials.  
6. If using S3, set `USE_S3=True` and bucket policy for public read of media paths as expected by `MEDIA_URL`.

---

## License and ownership

Proprietary to the Plants 99 / Ecomicx project unless otherwise stated elsewhere in the repository.

---

## Models & payments docs

See `docs/payments-and-models.md` for:

- The current `Order` / `Payment` / `Shipment` model summary
- How Razorpay payment verification aligns `Payment.status` and `Order.status`
- Current Shiprocket webhook → order status mapping
- Current state of vendor bank details (not implemented yet) and the recommended approach
