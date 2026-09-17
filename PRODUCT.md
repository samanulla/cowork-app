# CoWorkHub — Product Feature Document

> India-first, multi-tenant coworking-space management platform.
> Runs as a single SaaS deployment that serves many coworking businesses ("tenants"), with per-tenant branding, domain mapping, and localisation.

---

## 1. Who uses CoWorkHub?

| Persona | Role code | What they do |
| --- | --- | --- |
| Platform Owner (us) | `PLATFORM_OWNER` | Runs the SaaS. Provisions tenants, suspends/reactivates them, monitors platform health. Sees all tenants. |
| Tenant Super Admin | `SUPER_ADMIN` | Owner of a coworking business (e.g. CoWorkHub, Adyar Space, Winn Space). Full control of their own tenant. |
| Tenant Manager | `MANAGER` | Day-to-day operator. Cannot change tenant settings, audit log, or staff salary. |
| Location Manager | `LOCATION_MANAGER` | Scoped to a single location. |
| Company Admin | `COMPANY_ADMIN` | Represents a company customer of the tenant. Manages employees, subscriptions, invoices. |
| Employee | `EMPLOYEE` | Employee of a company customer. Books using company credits. |
| Individual Member | `INDIVIDUAL` | Freelancer / independent member with their own subscription. |

---

## 2. Sign-up flows

- **Tenant provisioning** — Platform Owner at `/platform/tenants/new` (auto-fills `<slug>.<PLATFORM_BASE_DOMAIN>` if primary_domain left blank) or CLI `flask create-tenant …`.
- **Company (self-serve)** — `/auth/register/company` → PROSPECT company + COMPANY_ADMIN user + auto-email to tenant super admins for approval.
- **Company (admin-created)** — `/admin/companies/new`.
- **Employee** — Company Admin fills name+email at `/company/employees/new`; system emails a signed **invitation link** (7-day TTL). Invitee sets their own password at `/company/invite/<token>`.
- **Individual** — fully self-serve at `/auth/register`.
- **Platform Owner** — created out of band with `flask create-admin --platform-owner …`.

---

## 3. Account management

- **Login** at `/auth/login` (rate-limited 10/min, 30/hr per IP).
- **Password reset** at `/auth/forgot-password` — sends a signed link (2-hour TTL); reset at `/auth/reset-password/<token>`.
- **Password change** at `/auth/change-password` (requires current password).
- **Two-factor auth (TOTP)** at `/auth/2fa/status` — pyotp-based, QR provisioning at `/auth/2fa/setup`. Login flow detects 2FA-enabled users and prompts at `/auth/2fa/login`.
- **Workspace picker** at `/auth/pick-workspace` for users on the apex domain.

---

## 4. Product modules

### Platform (`/platform/*`)
Dashboard, tenant CRUD + provision, suspend/activate. All actions audit-logged.

### Admin — tenant back office (`/admin/*`)
- **Locations, Floors, Seats, Rooms** — inventory + amenities + operating hours per location.
- **Companies** — CRUD + KYC document upload (S3 / local / Azure Blob).
- **Pricing Plans** — hot desk / dedicated / private office / all-access / day pass; monthly + daily cycles.
- **Subscriptions & Allocations** — link seats to subscriptions.
- **Bookings** — seat + room calendars.
- **Billing** — invoices, line items, payments (UPI / NEFT / RTGS / IMPS / Card / Cash / Cheque), credit notes, refunds (with pending → completed/failed lifecycle). **PDF export** at `/admin/invoices/<id>/pdf`.
- **Expenses** — categories, claims, approve/reject/mark-paid workflow.
- **Staff & Payroll** — records, salary history, payroll runs.
- **Email templates** — per-tenant.
- **Reports** — Occupancy, Financials, Subscriptions, People, **Capacity Heatmap** (`/admin/reports/heatmap`) — all Chart.js.
- **System Settings** — tenant identity, tax rate, invoice prefix, formats.
- **Audit log** — filterable by action/actor/date, **CSV export**.
- **Reception** — day-pass QR scan (`/admin/reception`) and visitor check-in/out (`/hub/reception/visitors`).

### Company (`/company/*`)
Dashboard, employees CRUD (with **email invitations**), team bookings visibility, subscriptions, invoices, allocations.

### Member (`/me/*` and `/hub/*`)
- Dashboard, seat + room bookings, cancel-with-refund.
- **Day passes** — `/me/day-passes` → issue → QR at `/me/day-passes/<id>/qr.png`.
- **Community hub** (`/hub/*`):
  - **Directory** — opt-in profile with headline, bio, skills, LinkedIn.
  - **Announcements** — pinnable, optionally scoped to a location.
  - **Guest passes** — issue a day pass for a visiting client.
  - **Visitor pre-registration** — reception can check them in/out.
  - **Support tickets** — subject/body/priority, admin resolves.
  - **Printing credits** — ledger balance, admin adjusts.
  - **Lockers** — admin CRUD, assign/release per user.
  - **Refer & earn** — creates a code + reward_credits for each referral.

### Booking add-ons (`/book/*`)
Recurring room bookings (daily/weekly patterns), waitlist for full slots.

---

## 5. Multi-tenancy model

- **Shared code, shared DB.** Every business-scoped table has a `tenant_id` FK (`ON DELETE CASCADE`), indexed.
- **Automatic scoping.** A `do_orm_execute` SQLAlchemy listener injects `tenant_id = <current> OR tenant_id IS NULL` on every SELECT. Platform-Owner routes opt out with `.execution_options(skip_tenant_filter=True)`.
- **Tenant resolution.** `before_request` matches the `Host` header against `Tenant.primary_domain` / `Tenant.custom_domain`. `g.tenant_id` cached at request time to avoid ORM-attribute recursion in the listener.
- **Dedicated deployment mode** via `DEPLOY_MODE=dedicated` + `TENANT_ID=<n>`.
- **Per-tenant branding** — name, logo, brand colour, tagline, support email — surfaced in `base.html`.
- **Per-tenant localisation** — currency, symbol, locale, timezone, date/datetime/time format, tax rate, tax label, invoice prefix, GSTIN, PAN, legal name.
- **Email uniqueness per tenant** — `UniqueConstraint(tenant_id, email)` so `john@gmail.com` can register with Adyar *and* Winnspace as two independent accounts. Platform Owner row (`tenant_id IS NULL`) enforced globally-unique by a partial index.

---

## 6. Localisation (India-first defaults)

- **Currency**: INR, symbol `₹`, Indian number grouping (`1,23,45,678`).
- **Timezone**: `Asia/Kolkata`.
- **Date**: `%d-%b-%Y`. **Datetime**: `%d-%b-%Y %I:%M %p`.
- **Tax**: 18% GST default.
- **Payment methods**: UPI / NEFT / RTGS / IMPS / Card / Cash / Cheque.

Every value is per-tenant, editable from Settings.

---

## 7. Security posture

- Passwords hashed with Werkzeug (`pbkdf2:sha256`).
- Flask-Login session cookies (HTTPS-only in production, `SameSite=Lax`).
- CSRF via Flask-WTF on every form.
- **Rate limiting** — Flask-Limiter: login POST 10/min, 30/hr per IP; forgot-password 5/min, 20/hr.
- **Two-factor auth (TOTP)** — pyotp; QR provisioning; verify with 1-window clock drift tolerance.
- **`_safe_next()`** — blocks external redirects, non-absolute paths, and `/auth/logout`.
- **Audit log** — actor/IP/user-agent for every sensitive mutation; filterable + CSV export.
- **Auto-scoping** — defence in depth against cross-tenant data leaks.

---

## 8. Deployment

- **Local dev**: `docker compose up -d db`, then `flask db upgrade && flask seed-demo && flask run`.
- **Email**: Flask-Mail (SMTP) — works with local MailHog or **AWS SES SMTP** (see [.env.example](.env.example)). Set `MAIL_SUPPRESS_SEND=true` for tests.
- **AWS**: EC2 + RDS PostgreSQL + S3 for documents + SES for email. See [`deploy/aws-setup.md`](deploy/aws-setup.md).
- **Storage**: cloud-agnostic (`STORAGE_BACKEND=s3|azure_blob|local`).
- **Reset test data**: see the "Resetting the database" section in [README.md](README.md).

---

## 9. What's shipped (5 phases, 47 tests)

| Phase | Commit | Features |
| --- | --- | --- |
| Foundational | `0e86e5b` → `582a52b` | 55 routes, admin/company/member portals, India-first, 10 audit fixes |
| Multi-tenant | `678abbf` | Tenant model, PLATFORM_OWNER, per-tenant branding + localisation, `/platform/*` |
| Per-tenant email | `b244015` | `UniqueConstraint(tenant_id, email)` + partial index for platform owner |
| Phase 1 | `7abd4be` | Password reset + change UI + workspace picker + SMTP mail (SES-ready) |
| Phase 2 | `833c698` | Employee email invitations + company approval email + tenant slug auto-fill + session hardening + day-pass QR + reception |
| Phase 3 | `5c7bba5` | 2FA (TOTP) + audit filters/CSV + capacity heatmap + PDF invoices + waitlist + recurring bookings |
| Phase 4 | `7284da9` | Guest passes, visitors, community directory, announcements, printing credits, support tickets, lockers, referrals |
| Phase 5 | (this) | Modern marketing landing + colourful theme + Inter font + role-based sign-in cards + feature grid |

---

## 10. Roadmap (still open, low priority)

- **Wildcard-cert automation** for tenant custom domains.
- **All-Access cross-location booking** (mostly plumbed, needs UI polish).
- **Platform-side subscription billing** (charging tenants for the SaaS itself).
- **Read replicas** for report queries.
- **Mobile-app JWT API** (blueprint stub exists at `/api/v1`).

---

_Last updated: 2026-09-16._
