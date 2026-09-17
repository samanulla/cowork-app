# CoWorkHub — Product Feature Document

> India-first, multi-tenant coworking-space management platform.
> Runs as a single SaaS deployment that serves many coworking businesses ("tenants"), with per-tenant branding, domain mapping, and localisation.

---

## 1. Who uses CoWorkHub?

| Persona | Role code | What they do |
| --- | --- | --- |
| Platform Owner (us) | `PLATFORM_OWNER` | Runs the SaaS. Provisions tenants, suspends/reactivates them, monitors platform health. Sees all tenants. Does not touch tenant business data. |
| Tenant Super Admin | `SUPER_ADMIN` | Owner of a coworking business (e.g. CoWorkHub, Adyar Space, Winn Space). Full control of their own tenant: locations, staff, billing, settings, audit log. |
| Tenant Manager | `MANAGER` | Day-to-day operator of the tenant. Locations, seats, rooms, bookings, invoices, reports. Cannot change tenant settings, audit log, or staff salary. |
| Location Manager | `LOCATION_MANAGER` | Scoped to a single location. Manages seats/rooms/bookings there. |
| Company Admin | `COMPANY_ADMIN` | Represents a company customer of the tenant. Manages their employees, subscriptions, and invoices. |
| Employee | `EMPLOYEE` | Employee of a company customer. Books seats/rooms using company credits. |
| Individual Member | `INDIVIDUAL` | Freelancer / independent member with their own subscription. |

Roles are hierarchical: PLATFORM_OWNER > SUPER_ADMIN > MANAGER > LOCATION_MANAGER; COMPANY_ADMIN > EMPLOYEE.

---

## 2. Sign-up & onboarding flows

There is no single "sign-up" — the right flow depends on who you are.

### 2.1 A new tenant (coworking business) joins CoWorkHub

**Flow: Platform-Owner provisions.**

1. The Platform Owner signs in at `/auth/login` (routed to `/platform/`).
2. Opens **Platform → Tenants → Provision tenant** (`/platform/tenants/new`).
3. Fills in tenant details (slug, brand name, primary domain, currency, tz, tax, invoice prefix) **and** the first admin's name/email/password.
4. On save, the platform creates:
   - The `Tenant` row.
   - Default pricing plans + email templates for the tenant.
   - The first `SUPER_ADMIN` user (belongs to that tenant).
5. Platform Owner shares the admin credentials with the tenant out-of-band (email/secure channel).
6. The tenant admin signs in at their domain (or the shared login) and **should change the password from Settings → Profile** (password change UI is a follow-up item — see §9).

_A CLI equivalent exists for scripted onboarding: `flask create-tenant --slug ... --name ... --primary-domain ... --admin-email ... --admin-password ...`._

### 2.2 A company signs up with a tenant

Two paths, both supported:

- **Self-serve** at `/auth/register/company` — the company admin fills a form, we create a `Company` in `PROSPECT` status plus their `COMPANY_ADMIN` login. The tenant admin later approves + activates the company.
- **Admin-created** — the tenant admin (or manager) creates the company at `/admin/companies/new` and shares the company admin's credentials.

### 2.3 An employee joins a company

**Flow: Company Admin invites (credentialed).**

The company admin creates the employee at `/company/employees/new`, enters a temporary password, and shares it with the employee. The employee signs in and (should) change their password. A self-serve email-invite flow is a planned enhancement (see §9).

### 2.4 An individual member joins

**Flow: fully self-serve** at `/auth/register`. The user creates an account (email + password), lands in `/me/`, browses locations & rooms, and can subscribe / book.

### 2.5 Platform Owner accounts

There is no public sign-up for Platform Owner. Create one with:

```powershell
flask create-admin --email you@coworkhub.io --password ChangeMe123! --platform-owner
```

---

## 3. Product modules

### 3.1 Platform administration (`/platform/*`)

- Dashboard with tenant counts, user counts, revenue snapshot.
- Tenant list with plan tier, status (Trial / Active / Suspended / Churned), user & location counts.
- Provision new tenant.
- Edit tenant branding, domain, localisation, tax, GSTIN.
- Suspend / reactivate tenant.
- All actions logged to `AuditLog`.

### 3.2 Tenant administration (`/admin/*`)

- **Dashboard** — occupancy, MRR, active subscriptions, recent bookings.
- **Locations, Floors, Seats, Rooms** — full inventory management, per-location operating hours, amenities.
- **Companies** — CRUD, KYC document upload (S3 / local / Azure Blob via `StorageService`).
- **Pricing Plans** — hot desk / dedicated / private office / all-access / day pass, monthly or daily cycles.
- **Subscriptions & Allocations** — assign a seat to a subscription, end an allocation.
- **Bookings** — seat + room booking calendars.
- **Billing** — invoices, invoice lines, payments (UPI / NEFT / RTGS / IMPS / Card / Cash / Cheque), credit notes, refunds (with full lifecycle: pending → completed/failed).
- **Expenses** — categories, expense claims, approve/reject/mark-paid workflow.
- **Staff & Payroll** — staff records, salary history, payroll runs (approve → mark-paid).
- **Email templates** — customisable per tenant.
- **Reports** — Occupancy, Financials, Subscriptions, People (all with Chart.js).
- **System Settings** — tenant identity, tax rate, invoice prefix, number/date formats.
- **Audit log** — every mutation of pricing/billing/tenants/users is recorded.

### 3.3 Company workspace (`/company/*`)

- Dashboard with team headcount, credit usage, upcoming renewals.
- Employees CRUD.
- Bookings visibility across team.
- Subscriptions & invoices for the company.
- Allocations (which employee has which desk).

### 3.4 Member workspace (`/me/*`)

- Dashboard with active subscriptions, credits, upcoming bookings.
- Seat bookings + room bookings with cancel-with-refund (returns credits when applicable).

---

## 4. Multi-tenancy model

- **Shared code, shared database.** Every business-scoped table has a `tenant_id` column (indexed, FK → `tenants.id`, `ON DELETE CASCADE`).
- **Automatic scoping.** A `do_orm_execute` SQLAlchemy event listener injects `tenant_id = <current> OR tenant_id IS NULL` on every SELECT for tenant-scoped models. Platform-Owner routes opt out with `.execution_options(skip_tenant_filter=True)`.
- **Tenant resolution.** `before_request` reads the `Host` header and matches against `Tenant.primary_domain` / `Tenant.custom_domain`. Falls back to the first tenant for `localhost` / dev.
- **Dedicated deployment mode** (single tenant per deployment) is supported via `DEPLOY_MODE=dedicated` + `TENANT_ID=<n>` env vars.
- **Per-tenant branding** (name, logo, brand colour, tagline, support email) is injected into `base.html` at every render.
- **Per-tenant localisation** (currency, symbol, locale, timezone, date/datetime/time format, tax rate, tax label, invoice prefix, GSTIN, PAN, legal name) lives on the `Tenant` row and is read by the formatting service on every request.
- **Email addresses are unique per tenant, not globally.** The same email (say `john@gmail.com`) can register with Adyar and Winnspace as two independent accounts — each with its own password. The `Host` header (the URL the user visits) selects the tenant before authentication, so login is unambiguous. Enforced by `UniqueConstraint(tenant_id, email)`. The Platform Owner row (`tenant_id IS NULL`) is separately enforced globally-unique by a partial index.

---

## 5. Localisation (India-first defaults)

- **Currency**: INR, symbol `₹`, Indian number grouping (`1,23,45,678`).
- **Timezone**: `Asia/Kolkata` for all datetime rendering.
- **Date format**: `%d-%b-%Y` (e.g. `16-Sep-2026`).
- **Datetime format**: `%d-%b-%Y %I:%M %p`.
- **Tax**: 18% GST default, configurable.
- **Payment methods**: UPI / NEFT / RTGS / IMPS in addition to Card / Cash / Cheque.

Every value above is per-tenant and editable from Settings.

---

## 6. Security posture

- Passwords hashed with Werkzeug (`pbkdf2:sha256` by default).
- Flask-Login session cookies (HTTPS-only in production).
- CSRF via Flask-WTF on every form.
- **Rate limiting** via Flask-Limiter: login POST is capped at `10/min; 30/hr` per IP.
- **`_safe_next()`** on login blocks external redirects, non-absolute paths, and redirects back to `/auth/logout`.
- **AuditLog** captures actor + IP + user-agent for every sensitive mutation (tenant CRUD, invoice void, refund complete, plan changes, settings updates, etc.).
- All queries auto-scoped by `tenant_id` — defence in depth against cross-tenant data leaks.

---

## 7. Navigation map

```
Platform Owner              Tenant Super Admin / Manager        Company Admin           Member / Employee
─────────────────           ────────────────────────────        ──────────────          ─────────────────
/platform/                  /admin/                              /company/                /me/
/platform/tenants           /admin/locations                     /company/employees       /me/bookings
/platform/tenants/new       /admin/companies                     /company/subscriptions
                            /admin/plans                         /company/invoices
                            /admin/allocations                   /company/allocations
                            /admin/invoices                      /company/bookings
                            /admin/credit-notes                  /company/plans
                            /admin/refunds
                            /admin/expenses
                            /admin/expense-categories
                            /admin/staff
                            /admin/payroll
                            /admin/email-templates
                            /admin/reports
                            /admin/settings          (SA only)
                            /admin/audit-log          (SA only)
```

---

## 8. Deployment

- **Local dev**: PostgreSQL via `docker-compose up -d postgres`, then `flask db upgrade && flask seed-demo && flask run`.
- **AWS**: EC2 + RDS PostgreSQL + S3 for documents + SES for email. See [`deploy/aws-setup.md`](deploy/aws-setup.md).
- **Storage** is cloud-agnostic (`StorageService` abstraction) — swap `STORAGE_BACKEND=s3|azure_blob|local` via env vars.

---

## 9. Known gaps / roadmap

- **Password change UI** for users (currently only settable at creation).
- **Password reset** via email token.
- **Email invite** flow for employees (today: admin gives them a temp password out-of-band).
- **Wildcard-cert automation** for tenant custom domains.
- **Platform-side subscription billing** (charging tenants for the SaaS itself) — deferred; platform-admin does not need to see per-tenant company/individual pricing.
- **Two-factor authentication.**
- **Read replicas** for report queries.

---

_Last updated: 2026-09-16._
