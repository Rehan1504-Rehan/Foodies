<div align="center">

# 🍔 FOODIES

### Good Food. Great Mood.

A complete, production-shaped food delivery platform — four separate interfaces
(**Customer**, **Restaurant Owner**, **Delivery Partner**, **Admin**) running on one
Django + DRF backend and one relational database.

`Python 3.11` · `Django 5.1` · `Django REST Framework` · `PostgreSQL / SQLite` · `Bootstrap 5` · `WhiteNoise` · `Gunicorn`

</div>

---
## Live site 
- https://foodies-68y6.onrender.com
- The site is live but if render black interface comes please wait for 2 minutes for render to activate site.

## ✨ What is inside

| Area | Highlights |
|---|---|
| **Customer app** | Location-aware homepage, restaurant & category browsing, menu with ADD / +/−, search with filters (rating, price, delivery time, veg, cuisine, offers), favourites, cart, coupons, checkout, COD + Razorpay/mock payments, live order tracking, order history, invoices, reviews, notifications, profile & address book |
| **Restaurant owner console** | Dashboard KPIs (today's orders, pending, revenue, popular dish), order buckets (New → Confirmed → Preparing → Ready → Completed → Cancelled) with Accept / Reject / Start Preparing / Mark Ready, menu & category management with image upload, offers, review replies, sales analytics, restaurant profile |
| **Delivery partner app** | Online/offline toggle, today's/completed/pending deliveries, available deliveries feed with one-tap claim, assigned job detail with address + distance, status updates (Accepted → Picked Up → Out for Delivery → Delivered), earnings (today/week/month/total) and payout history, vehicle profile |
| **Admin console** | Totals + charts (daily orders, weekly/monthly revenue, top restaurants, popular food), customer / owner / partner management with block & unblock, restaurant approvals, categories & food catalogue, order monitoring, delivery assignment, payments, coupons, reviews, reports, settings |
| **Security** | Email-based custom user, hashed passwords, role decorators + DRF permission classes, object-level scoping (no cross-customer / cross-restaurant / cross-partner data), CSRF everywhere, validated uploads, server-side pricing, env-var secrets |
| **Platform** | PostgreSQL in production / SQLite locally, WhiteNoise static serving, media uploads, REST API at `/api/`, Django admin at `/admin/`, `seed_data` demo dataset, branded 400/403/404/500 pages |

---

## 🚀 Quick start (local, SQLite)

```bash
# 1. Clone
git clone https://github.com/<your-username>/Foodies.git
cd Foodies

# 2. Virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Environment
cp .env.example .env              # then edit SECRET_KEY etc. (optional for dev)

# 5. Database
python manage.py migrate

# 6. Demo data (restaurants, menus, users, orders…)
python manage.py seed_data

# 7. Run
python manage.py runserver
```

Open <http://127.0.0.1:8000/> — you are on the FOODIES homepage.

### Demo logins created by `seed_data`

| Role | User ID / Email | Password |
|---|---|---|
| Admin | `ADMIN` at `/admin/` | `Password@123` |
| Customer | `rahul@foodies.test` | `Foodies@123` |
| Restaurant owner | `owner@foodies.test` | `Foodies@123` |
| Delivery partner | `rider@foodies.test` | `Foodies@123` |

> `python manage.py seed_data --flush` wipes the demo data first,
> `--orders 60` controls how many orders are generated.

---

## 🧭 Where everything lives

```
/                       Customer website (home, search, offers, about, contact)
/restaurants/           Restaurant list + detail (approved restaurants only)
/categories/            Category browse
/cart/  /checkout/      Cart, coupons, checkout, payment, history
/orders/                Order history, detail, tracking, invoice
/reviews/               Write / manage reviews
/accounts/              Login, register (customer/owner/partner), profile, addresses, notifications
/admin/                 Django's built-in admin (login: ADMIN / Password@123)
/admin-dashboard/       FOODIES admin console
/restaurant-dashboard/  Restaurant owner console
/delivery/              Delivery partner app
/customer/              Customer dashboard (post-login landing)
/django-admin/          Legacy alias — redirects to /admin/
/api/                   REST API (browsable)
/healthz/               Health check for Render/Railway
```

---

## 🔌 REST API (all under `/api/`)

| Endpoint | Purpose |
|---|---|
| `auth/register/`, `auth/login/`, `auth/logout/`, `auth/token/`, `auth/me/` | Token/session auth |
| `restaurants/`, `restaurants/<slug>/`, `restaurants/<slug>/menu/`, `restaurants/<slug>/favorite/` | Browse restaurants & menus |
| `categories/`, `food/` | Catalogue with search / ordering / price filters |
| `cart/`, `cart/add/`, `cart/update/`, `cart/remove/`, `cart/clear/`, `cart/coupon/`, `cart/coupon/remove/` | Server-priced cart |
| `orders/`, `orders/checkout/`, `orders/<no>/`, `orders/<no>/track/`, `orders/<no>/cancel/` | Ordering & tracking |
| `payments/`, `payments/config/`, `payments/confirm/`, `payments/order/<no>/create/`, `payments/<id>/` | COD / Razorpay / mock |
| `reviews/`, `reviews/order/<no>/` | Delivered orders only |
| `delivery/assignments/`, `delivery/profile/` | Partner's own jobs only |
| `notifications/`, `notifications/unread-count/` | DB-backed notifications |

Every endpoint is role-scoped with DRF permission classes — a customer gets `403`
on delivery/admin endpoints, a partner only ever sees their own assignments.

---

## ⚙️ Configuration

All secrets come from environment variables (`.env` locally, dashboard vars in
production). Nothing is hard-coded.

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret (required in production) |
| `DEBUG` | `True` locally, `False` in production |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Hosts allowed to serve the app |
| `DATABASE_URL` | `postgresql://…` in production, empty → SQLite locally |
| `MEDIA_ROOT` | Mounted disk for uploads (Render/Railway) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Live payments |
| `PAYMENTS_MOCK_MODE` | `True` → built-in mock gateway (no real money) |
| `TAX_RATE`, `PLATFORM_FEE`, `DEFAULT_DELIVERY_FEE`, `FREE_DELIVERY_ABOVE`, `RESTAURANT_COMMISSION_RATE`, `DEFAULT_DELIVERY_EARNING` | Business rules |
| `EMAIL_*` | SMTP for notifications/password reset |
| `ADMIN_LOGIN_ID`, `ADMIN_LOGIN_PASSWORD` | Optional admin login overrides (default: `ADMIN` / `Password@123`) |
| `SEED_DATA` | Set `True` on a deploy to load demo data |

---

## 🐘 PostgreSQL (production)

```bash
# Local PostgreSQL
createdb foodies
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/foodies"
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

`dj-database-url` also understands `postgres://`, `sqlite:///`, and Render's
`DATABASE_URL`, so no code changes are needed between environments.

---

## ☁️ Deployment

### Render (blueprint included)

1. Push this repository to GitHub.
2. Render → **New → Blueprint** → select the repo (`render.yaml` is detected).
3. Render creates the web service **and** a PostgreSQL database, generates a
   `SECRET_KEY`, mounts a 5 GB disk for `MEDIA_ROOT` and runs
   `./build.sh` (install → `collectstatic` → `migrate`).
4. Add `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` if you want live payments
   (otherwise the mock gateway stays active).
5. Optionally set `SEED_DATA=True` for one deploy to load the demo dataset.

### Railway

1. Railway → **New Project → Deploy from GitHub repo**.
2. Add the **PostgreSQL** plugin — `DATABASE_URL` is injected automatically.
3. Variables: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=*`,
   `MEDIA_ROOT=/data/media` (+ attach a volume at `/data`).
4. Deploy command uses the `Procfile`; or set
   `bash build.sh && gunicorn foodies.wsgi:application --bind 0.0.0.0:$PORT`.

### Any VPS / Docker-less host

```bash
export DEBUG=False SECRET_KEY=... DATABASE_URL=... ALLOWED_HOSTS=yourdomain.com
./build.sh
gunicorn foodies.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

Uploads are served from `MEDIA_ROOT`; keep it on a persistent volume so food
photos survive redeploys.

---

## 🧪 Tests

```bash
python manage.py test tests        # 89 tests
```

The suite covers registration, RBAC matrix, object-level security, the pricing
engine (item discounts, delivery thresholds, minimum order, coupon rules),
order lifecycle & cancellation, delivery assignment/claim/earnings, reviews,
REST API contracts and the full four-role end-to-end journey
(`tests/test_end_to_end.py`).

Smoke-check other things by hand:

```bash
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
```

---

## 🗂️ Project layout

```
Foodies/
├── foodies/          # settings, root urls, wsgi/asgi, template tags, error views
├── accounts/         # custom user, addresses, auth, RGPD-ish profile, notifications
├── restaurants/      # restaurants, approval flow, favourites
├── menu/             # categories + food items (Pillow uploads)
├── cart/             # cart models + server-side pricing engine
├── orders/           # orders, items, status history, notifications, services
├── payments/         # Payment model, COD/Razorpay/mock services
├── delivery/         # partner profiles, assignments, earnings
├── reviews/          # delivered-order reviews + owner replies
├── offers/           # coupons + redemptions
├── dashboard/        # admin / owner / customer dashboards + sidebar shells
├── templates/        # partials, customer, restaurant, delivery, admin, errors
├── static/           # design system CSS, JS, brand images
├── media/            # user uploads (gitignored)
├── tests/            # automated test-suite
├── build.sh · render.yaml · Procfile · requirements.txt · .env.example
```

---

## 🔐 Security checklist

- Passwords are hashed by Django's auth system; custom email login.
- Role-based decorators **and** DRF permission classes on every private view.
- Querysets are always scoped: customers see only their orders, owners only
  their restaurant, partners only their own delivery jobs.
- Checkout runs inside `transaction.atomic()` — no half-created orders.
- Prices, discounts, coupons and taxes are recomputed server-side on every
  request; the browser is never trusted for money.
- CSRF protection on all POST forms, validated file uploads, ORM-only queries.
- Secrets live in environment variables; `.env` is gitignored.

---

<div align="center">

**FOODIES** — *Good Food. Great Mood.* 🍕🛵

</div>
