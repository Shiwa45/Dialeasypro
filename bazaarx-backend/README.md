# BazaarX Backend

Multivendor e-commerce platform backend — **NestJS + TypeScript**.

Databases: **PostgreSQL** (core), **MongoDB** (logs/specs/cart), **Redis** (cache/OTP/sessions), **Elasticsearch** (search).

---

## Prerequisites

- Node.js 20 LTS
- Docker + Docker Compose
- npm

---

## Quick Start (Local Dev)

```bash
# 1. Install dependencies
npm install

# 2. Copy env file (already has working dev defaults)
cp .env.example .env

# 3. Start all databases (Postgres, Mongo, Redis, Elasticsearch, Kibana)
docker compose up -d

# 4. Wait ~30s for Elasticsearch to be healthy, then start the app
npm run start:dev
```

The API will be available at:

- API base: `http://localhost:3000/api/v1`
- Health check: `http://localhost:3000/api/v1/health`
- Swagger docs: `http://localhost:3000/docs`
- Kibana (ES UI): `http://localhost:5601`

---

## Project Structure

```
src/
├── config/              # Typed configuration + env validation
│   ├── configuration.ts # All env vars mapped to typed objects
│   └── env.validation.ts# Fails boot if required env missing
├── common/              # Shared building blocks (Module 3)
│   ├── filters/         # Global exception filter
│   ├── interceptors/    # Response transform interceptor
│   ├── decorators/      # Custom decorators
│   ├── dto/             # Pagination DTOs
│   ├── pipes/           # Custom pipes
│   └── guards/          # Auth guards
├── database/            # DB connection modules (Module 2)
├── modules/             # Feature modules
│   └── health/          # Health check (Kubernetes probes)
├── app.module.ts        # Root module
└── main.ts              # Bootstrap (security, CORS, versioning, Swagger)
```

---

## Available Scripts

| Command | Description |
|---|---|
| `npm run start:dev` | Start with hot-reload |
| `npm run build` | Compile to `dist/` |
| `npm run start:prod` | Run compiled build |
| `npm run lint` | Lint and auto-fix |
| `npm test` | Run unit tests |
| `npm run migration:generate` | Generate TypeORM migration |
| `npm run migration:run` | Apply migrations |

---


## Auth Endpoints (Module 4)

All under `/api/v1/auth`. OTP is printed to the console in dev (no SMS cost).

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/send-otp` | public | Send OTP to a mobile number |
| POST | `/verify-otp` | public | Verify OTP; register if new; return JWT pair |
| POST | `/refresh-token` | public | Rotate refresh token → new pair |
| POST | `/logout` | public | Revoke one refresh token (this device) |
| POST | `/logout-all` | bearer | Revoke all sessions (everywhere) |
| GET | `/me` | bearer | Current authenticated user |

**Security model:** every route is protected by a global JWT guard; opt out with `@Public()`. Refresh tokens are hashed and tracked in Redis, rotated on each use (reuse of an old token is detected and rejected). OTP has resend cooldown + bounded verify attempts.


## User & Address Endpoints (Module 5)

All under `/api/v1/users`, all require a bearer token.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/me` | Full profile |
| PATCH | `/me` | Update profile (name, DOB, gender, language) |
| GET | `/me/addresses` | List saved addresses (default first) |
| POST | `/me/addresses` | Add address (first is auto-default) |
| PATCH | `/me/addresses/:id` | Update an address |
| POST | `/me/addresses/:id/set-default` | Make address default |
| DELETE | `/me/addresses/:id` | Delete (auto-promotes next default) |

**Invariant:** exactly one default address per user, enforced transactionally.



## Seller Endpoints (Phase 1 · Module 2)

Under `/api/v1/sellers`, all require a bearer token.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/register` | any user | Apply to become a seller (GST/PAN/bank + KYC docs) |
| GET | `/me` | self | My application/profile + status |
| PATCH | `/me` | self | Update store/bank details |
| GET | `/admin/pending` | admin | Applications awaiting review |
| POST | `/:id/approve` | admin | Approve → promotes user role to seller |
| POST | `/:id/reject` | admin | Reject with reason |
| POST | `/:id/suspend` | admin | Suspend a seller |

**Approval flow:** a buyer applies → admin approves → the user's role is promoted to `seller` in the same transaction, unlocking product listing. GSTIN/PAN/IFSC are format-validated; GSTIN is unique across sellers.


## Search Endpoints (Phase 1 · Module 3)

Under `/api/v1/search`.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/search?q=&categoryId=&brand=&minPrice=&maxPrice=&sort=` | public | Full-text search + filters + facets |
| GET | `/search/suggest?q=` | public | Autocomplete (search-as-you-type) |
| POST | `/search/reindex` | admin | Rebuild the whole index from Postgres |

**How it stays in sync:** the catalogue emits `product.published` / `product.unpublished` events (on moderation, update, delete); the search module listens and indexes/removes the product in Elasticsearch. The two modules are fully decoupled — catalogue never imports search. Search features typo tolerance (fuzziness), field boosting (`title^3`), brand facets, and price stats for the filter sidebar.


## Cart Endpoints (Phase 1 · Module 4)

Under `/api/v1/cart`, all require a bearer token. Cart lives in **Redis** (cross-device, 7-day TTL).

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/cart` | Get cart (enriched with live price & stock) |
| POST | `/cart/items` | Add item (variantId + quantity) |
| PATCH | `/cart/items/:variantId` | Update quantity |
| DELETE | `/cart/items/:variantId` | Remove item |
| DELETE | `/cart` | Clear cart |
| GET | `/cart/saved` | Saved-for-later list |
| POST | `/cart/items/:variantId/save-for-later` | Move to saved |
| POST | `/cart/saved/:variantId/move-to-cart` | Move back to cart |

**Design:** only `variantId + quantity` is stored in Redis — never prices — so the cart always reflects current pricing/stock when read (enriched from Postgres). Stock is validated on add/update; totals (subtotal, MRP, savings) are computed live. All prices in paise.


## Checkout & Order Endpoints (Phase 1 · Module 5)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/checkout` | buyer | Place an order from the cart (COD) |
| GET | `/orders` | buyer | List my orders |
| GET | `/orders/:id` | buyer | Order detail |
| POST | `/orders/items/:itemId/cancel` | buyer | Cancel an item pre-dispatch (restores stock) |
| GET | `/seller/order-items` | seller | Items to fulfill |
| PATCH | `/seller/order-items/:itemId/status` | seller | Advance fulfillment status |

**Order placement guarantees:** stock is decremented atomically (a conditional `UPDATE ... WHERE stock >= qty`), so concurrent checkouts can't oversell — if any line fails, the whole transaction rolls back. Price, GST rate, and product details are snapshotted onto each order item (immutable history). The delivery address is frozen as JSON. Order numbers are human-readable (`ORD-2026-XXXXXXXX`). Per-item lifecycle: placed → confirmed → packed → shipped → out_for_delivery → delivered; COD payment settles to `paid` once all items are delivered. Free delivery above ₹499.




## Build Progress (Phase 4 — Advanced Commerce)

- [x] **Module 1** — Wallet & BNPL (store credit, top-ups, pay-with-wallet, refunds)
- [x] **Module 2** — Recommendations
- [x] **Module 3** — Admin panel & moderation
- [x] **Module 4** — ONDC adapter (Beckn protocol BPP)

## Wallet & BNPL Endpoints (Phase 4 · Module 1)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/wallet` | Balance |
| GET | `/wallet/transactions` | Ledger history |
| POST | `/wallet/topup` | Start a Razorpay top-up |
| POST | `/wallet/topup/verify` | Verify & credit |
| POST | `/wallet/topup/mock-pay` | [DEV] simulate top-up |
| GET | `/wallet/bnpl` | BNPL credit line |
| POST | `/wallet/bnpl/repay` | Repay BNPL from wallet |

**Wallet:** an immutable double-entry-style ledger (every credit/debit recorded with running balance), atomic balance updates under row locks. New payment methods `wallet` (debits balance, settles instantly) and `bnpl` (draws on a credit line) at checkout. COD refunds now credit the wallet for real. Top-ups go through Razorpay (dev-mock supported). BNPL has a per-user credit limit; repayment draws from the wallet.


## Recommendation Endpoints (Phase 4 · Module 2)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/products/:id/related` | public | Same-category products |
| GET | `/products/:id/frequently-bought-together` | public | Co-purchase analysis |
| GET | `/recommendations/trending` | public | Top sellers (30d) |
| GET | `/recommendations/for-you` | user | Personalized |
| POST | `/products/:id/view` | user | Record a view |
| GET | `/recommendations/recently-viewed` | user | Recently viewed |

**Recommendations:** explainable, query-driven heuristics over the catalogue and real purchase data. Frequently-bought-together is a co-purchase self-join on order items; "for you" recommends within categories the user has purchased in, excluding already-bought items (cold-start falls back to trending); trending ranks delivered units over 30 days (falls back to newest). Recently-viewed is a Redis list (deduped, recency-ordered). No new tables.


## Admin Panel Endpoints (Phase 4 · Module 3)

All under `/api/v1/admin`, admin-only.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/overview` | Platform KPIs + moderation backlog |
| GET | `/users?search=&role=` | List/search users |
| PATCH | `/users/:id/suspend` \| `/activate` | Block / restore login |
| PATCH | `/users/:id/role` | Change a user's role |
| GET | `/products/pending` | Product moderation queue |
| GET | `/sellers/pending` | Seller approval queue |
| GET | `/orders` | All orders (oversight) |
| PATCH | `/reviews/:id/hide` \| `/show` | Moderate reviews |

**Admin panel:** platform-wide oversight — KPIs (users, sellers, products, orders, GMV, GST collected) and a moderation backlog. User suspension toggles `isActive`, which the auth layer already enforces per request, so a suspended user is locked out immediately with no schema change. Review moderation flips visibility (hidden reviews drop out of public listings and rating aggregates). Admins can't suspend other admins.


## ONDC Adapter Endpoints (Phase 4 · Module 4)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/ondc/health` | Adapter status (subscriber id, mode, BPP role) |
| POST | `/ondc/search` | Beckn search → `on_search` catalog |
| POST | `/ondc/select` | → `on_select` (quote) |
| POST | `/ondc/init` | → `on_init` (billing/fulfillment) |
| POST | `/ondc/confirm` | → `on_confirm` (order) |
| POST | `/ondc/status` | → `on_status` (order status) |

**ONDC (Open Network for Digital Commerce):** a Beckn-protocol BPP (seller-side) adapter exposing BazaarX's catalogue to India's open commerce network. Each buyer-app action maps to its `on_*` callback with a properly built response context; `on_search` projects active products into a Beckn catalogue (providers → items with descriptors and pricing). Runs in unsigned mock mode locally; production signing keys drop in via config.

## Build Progress (Phase 3 — Growth & Engagement)

- [x] **Module 1** — Promotions & coupons (discounts, scoping, usage limits)
- [x] **Module 2** — Reviews & ratings (verified purchase)
- [x] **Module 3** — Notifications (SMS/email/push + in-app)
- [x] **Module 4** — Seller dashboard & analytics  ✅ **Phase 3 COMPLETE**

## Coupon Endpoints (Phase 3 · Module 1)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/coupons` | admin/seller | Create a coupon (sellers auto-scoped to self) |
| GET | `/coupons/active` | public | List active platform-wide coupons |
| GET | `/coupons` | admin | List all coupons |
| PATCH | `/coupons/:id/deactivate` | admin/seller | Deactivate a coupon |
| POST | `/coupons/validate` | buyer | Preview discount against the cart |
| POST | `/checkout` (couponCode) | buyer | Apply a coupon at checkout |

**Coupons:** percentage (with optional cap) or flat discounts, min-cart thresholds, validity windows, global + per-user usage limits, and scope (whole platform / category / seller). Validation runs against the live cart; the discount is applied to the order total and a redemption is recorded inside the checkout transaction (so usage counts stay consistent). Sellers can only issue coupons scoped to their own products.


## Review Endpoints (Phase 3 · Module 2)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/products/:productId/reviews` | buyer | Write a review (verified purchase) |
| GET | `/products/:productId/reviews` | public | List reviews |
| GET | `/products/:productId/reviews/summary` | public | Star breakdown + average |
| PATCH | `/reviews/:id` | buyer | Edit my review |
| DELETE | `/reviews/:id` | buyer/admin | Delete review |
| POST | `/reviews/:id/helpful` | buyer | Mark a review helpful |
| POST | `/reviews/:id/response` | seller/admin | Respond to a review |

**Reviews:** only buyers with a delivered (or returned) order item for the product can review it, one review per product per user. Each create/edit/delete recomputes the product's `avgRating` + `reviewCount` and emits `product.published` so the Elasticsearch index stays in sync. Helpful-votes are deduplicated per user; sellers can respond to reviews on their own products.


## Notification Endpoints (Phase 3 · Module 3)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/notifications` | user | List my notifications (inbox) |
| GET | `/notifications/unread-count` | user | Unread badge count |
| PATCH | `/notifications/:id/read` | user | Mark one read |
| POST | `/notifications/read-all` | user | Mark all read |
| GET | `/notifications/preferences` | user | Channel preferences |
| PATCH | `/notifications/preferences` | user | Toggle SMS/email/push |

**Event-driven:** the order, payment, shipping, and return flows emit lifecycle events on the global bus; a listener turns each into an in-app notification and fans it out to the user's enabled channels (SMS/email/push, dev-console stubs in the same pattern as OTP/Razorpay/Shiprocket). Covers order placed (buyer + seller), payment success, shipped, delivered, return requested/approved, and refund processed. The in-app inbox is always recorded; external channels are gated by per-user preferences and skip gracefully when no address is on file.


## Seller Dashboard Endpoints (Phase 3 · Module 4)

All under `/api/v1/seller/dashboard`, seller-only.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/overview` | KPIs: revenue, orders, units, rating, returns |
| GET | `/sales?period=7d\|30d\|12m` | Revenue/order trend over time |
| GET | `/orders-by-status` | Item counts & value by fulfillment status |
| GET | `/top-products?limit=` | Best sellers by revenue |
| GET | `/returns` | Return rate, by status & reason |
| GET | `/settlement` | Gross − commission − refunds = net payable |

**Analytics:** pure read-only aggregation over order items, reviews, and returns, scoped per seller. Settlement computes platform commission by joining items → products → categories (per-category rate), then subtracts refunds for the net payout. No new tables — reporting over existing data.


## Seller Dashboard Endpoints (Phase 3 · Module 4)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/seller/dashboard/overview` | seller | Headline KPIs (revenue, units, rating, returns) |
| GET | `/seller/dashboard/sales?period=7d\|30d\|12m` | seller | Sales trend bucketed by day/month |
| GET | `/seller/dashboard/orders-by-status` | seller | Item counts + value per fulfillment status |
| GET | `/seller/dashboard/top-products?limit=` | seller | Best sellers by delivered revenue |
| GET | `/seller/dashboard/returns` | seller | Return totals, rate, by-status, by-reason |
| GET | `/seller/dashboard/settlement` | seller | Gross − commission − refunds = net payable |

**Analytics:** read-only aggregations scoped per seller, sourced from order items, reviews, and returns. Platform commission is computed via a category-rate join (order_items → products → categories), so settlement reflects each category's real take rate. All money in paise.

## Build Progress (Phase 2 — Payments & Logistics)

- [x] **Module 1** — Payments (Razorpay): online checkout, signature verification, webhooks
- [x] **Module 2** — GST invoice PDF generation
- [x] **Module 3** — Logistics (Shiprocket): serviceability, AWB, tracking
- [x] **Module 4** — Returns & refunds  ✅ **Phase 2 COMPLETE**

## Payment Endpoints (Phase 2 · Module 1)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/checkout` (paymentMethod ≠ cod) | buyer | Creates order + Razorpay gateway order |
| POST | `/payments/verify` | buyer | Verify payment signature → mark paid |
| POST | `/payments/webhook` | public (signed) | Razorpay server-to-server events |
| POST | `/payments/mock/pay` | buyer | [DEV] simulate success (mock mode only) |

**Flow:** online checkout reserves stock and holds items in `pending_payment`; the gateway order id is returned for the Razorpay UI. On verified payment (client `verify` or webhook `payment.captured`), the order becomes `paid` and items release to `placed` for fulfillment. On `payment.failed`, reserved stock is restored and items cancelled. Signature checks use real HMAC-SHA256 with constant-time comparison. A dev-mock mode (no keys) makes the whole flow testable without a Razorpay account; COD still works unchanged.


## Invoice Endpoints (Phase 2 · Module 2)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/orders/:orderId/invoices` | buyer/seller/admin | List GST invoices for an order |
| GET | `/orders/:orderId/sellers/:sellerId/invoice.pdf` | buyer/seller/admin | Download a seller's GST invoice PDF |

**GST-compliant tax invoices:** one invoice per seller per order (each seller bills under their own GSTIN). The CGST+SGST (intra-state) vs IGST (inter-state) split is derived from the seller's GSTIN state code versus the buyer's delivery state. Each invoice carries HSN codes, per-line taxable value and tax, and a sequential number (`INV-2026-XXXXXXXX`). The fully-computed invoice is frozen as JSON so the PDF (rendered with pdfkit) can be regenerated identically. Generated on first request; access restricted to the order's buyer, the seller in question, or an admin.


## Logistics Endpoints (Phase 2 · Module 3)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/shipping/serviceability?deliveryPincode=&weightGrams=&cod=` | public | Courier options & delivery estimates |
| POST | `/seller/orders/:orderId/shipment` | seller | Create courier shipment & assign AWB |
| GET | `/shipments/:id/track` | buyer/seller/admin | Pull latest tracking |
| POST | `/shipping/webhook` | public (token) | Shiprocket tracking updates |

**Shiprocket integration:** a seller creates a shipment for their items in an order — the service calls Shiprocket to create the order and assign an AWB in one step, then moves those items to `shipped` with the tracking number. Tracking (via poll or webhook) advances shipment status; on `delivered`, the covered items move to `delivered` and COD orders settle to `paid`. Auth token is cached in Redis. Online orders can't ship until paid. A dev-mock mode (no Shiprocket creds) fabricates serviceability, AWB, and tracking so the whole flow is testable without an account.


## Returns & Refund Endpoints (Phase 2 · Module 4)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/returns` | buyer | Request a return on a delivered item |
| GET | `/returns` | buyer | List my returns |
| POST | `/returns/:id/cancel` | buyer | Withdraw a return request |
| GET | `/seller/returns` | seller | Returns on my items |
| POST | `/returns/:id/approve` | seller/admin | Approve & create reverse pickup |
| POST | `/returns/:id/reject` | seller/admin | Reject a return |
| POST | `/returns/:id/complete` | seller/admin | Mark received, refund & restock |

**Return lifecycle:** buyers raise a return on a `delivered` item within a 7-day window. Seller/admin approves (a Shiprocket reverse pickup is created and the reverse AWB stored) or rejects. On completion the refund is issued — **Razorpay refund** for prepaid orders, **wallet/source** for COD — the unit is restocked, and the order item moves to `returned`. Every state transition is validated and authorized (buyer owns the request; only the item's seller or an admin can approve/refund).

## Build Progress (Phase 1 — Core Marketplace)

- [x] **Module 1** — Catalogue (categories, brands, products, variants, moderation)
- [x] **Module 2** — Seller onboarding (business profile, KYC, approval)
- [x] **Module 3** — Search & discovery (Elasticsearch indexing)
- [x] **Module 4** — Cart (Redis-backed, stock-validated)
- [x] **Module 5** — Checkout + Orders (COD)  ✅ **Phase 1 COMPLETE**

## Catalogue Endpoints (Phase 1 · Module 1)

Categories `/api/v1/categories`, Brands `/api/v1/brands`, Products `/api/v1/products`.

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| GET | `/categories/tree` | public | Nested category tree |
| GET | `/categories/:slug` | public | Category by slug |
| POST/PATCH/DELETE | `/categories...` | admin | Manage categories |
| GET | `/brands` | public | List brands |
| POST/PATCH/DELETE | `/brands...` | admin | Manage brands |
| GET | `/products` | public | Browse (filter/sort/paginate) |
| GET | `/products/:slug` | public | Product detail |
| POST | `/products` | seller | Create draft |
| PATCH | `/products/:id` | seller | Update own |
| POST | `/products/:id/submit` | seller | Submit for review |
| GET | `/products/seller/mine` | seller | My products |
| GET | `/products/admin/pending` | admin | Review queue |
| POST | `/products/:id/moderate` | admin | Approve/reject |

**Listing lifecycle:** draft → pending_review → active (or rejected). Only `active` products are publicly visible. Prices stored in paise (integers) to avoid float money bugs.

## Build Progress (Phase 0)

- [x] **Module 1** — Project scaffolding + dev environment
- [x] **Module 2** — Database connections (TypeORM, Mongoose, Redis, ES)
- [x] **Module 3** — API boilerplate (response format, errors, pagination)
- [x] **Module 4** — Auth module (OTP, JWT, refresh rotation)
- [x] **Module 5** — User profile + Address models  ✅ **Phase 0 COMPLETE**
