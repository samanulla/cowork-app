# CoWorkHub — Coworking Space Portal

A production-ready Flask application for running a WeWork-style coworking space. Supports
multi-tenant SaaS-style workflows for platform admins, subscribing companies, employees,
and individual members.

**Configured out of the box for India** — INR (₹), Indian number grouping (12,34,56,789),
`Asia/Kolkata` timezone, `%d-%b-%Y` date format, and GST 18%. Every one of these is
editable from the super-admin **System settings** page, so you can run the same codebase
in any region.

## Feature summary

| Area | Capabilities |
|------|--------------|
| **Auth** | Email/password login, role-based access (Super Admin, CoWorkHub Manager, Location Manager, Company Admin, Employee, Individual), password reset hooks |
| **Locations** | Multi-city, multi-building, multi-floor hierarchy with amenities and operating hours |
| **Workspaces** | Hot desks, dedicated desks, private offices, and conference rooms with capacity, amenities, hourly/daily/monthly rates |
| **Companies** | Company onboarding, KYC document uploads (S3), employee roster, seat/office allocations, credit pools |
| **Subscriptions** | Pricing plans (Hot Desk, Dedicated Desk, Private Office, All-Access, Custom), monthly billing cycles, prorated changes, meeting-room credits |
| **Bookings** | Real-time seat booking, conference room booking with conflict detection, recurring bookings, check-in/check-out, cancellation policy |
| **Admin console** | Manage locations, floors, seats, rooms, pricing plans, companies, invoices, documents, occupancy analytics |
| **Back office** | Staff members, salary structures, monthly payroll runs, expense management (categories, receipts, approvals), credit notes, refunds, editable email templates |
| **Reports** | Occupancy (booking volume, top rooms, per-location inventory), Financials (revenue vs expenses trend, AR aging, invoice status), Subscriptions (MRR/ARR, plan mix, top customers), People (staff by department, new members, headcount) |
| **Localisation** | Configurable currency (defaults ₹ INR + Indian grouping), timezone (defaults Asia/Kolkata), date/datetime formats (defaults `%d-%b-%Y`), tax label + rate (defaults GST 18%), business identity (GSTIN, PAN, invoice prefix) — all editable by super admin |
| **Company console** | Onboard/offboard employees, allocate seats, view invoices, manage credits, upload company documents |
| **Employee/Individual** | Book seats and rooms, view bookings, download invoices, manage profile |
| **Billing** | Auto-generated monthly invoices, per-booking usage charges, credit tracking, downloadable PDFs (stub) |
| **Documents** | S3-backed document storage (contracts, KYC, invoices) with cloud-agnostic abstraction (Azure Blob ready) |
| **Notifications** | Booking confirmations & reminders (email hooks; extend with SES/SendGrid) |
| **APIs** | REST endpoints for mobile/kiosk clients (JWT stub) |

## Tech stack

- **Framework:** Flask 3 + Blueprints + Application Factory
- **ORM:** SQLAlchemy 2 + Flask-Migrate (Alembic)
- **Auth:** Flask-Login + Werkzeug password hashing
- **Forms:** Flask-WTF (CSRF, validation)
- **DB:** PostgreSQL (all environments — in-memory SQLite is used only by the pytest suite)
- **Object storage:** AWS S3 (boto3) with abstraction ready for Azure Blob
- **Frontend:** Server-rendered Jinja2 + Bootstrap 5 + Alpine.js
- **Runtime:** Gunicorn on Docker
- **Secrets:** `.env` locally, AWS Secrets Manager / Azure Key Vault in prod

## Project layout

```
cowork-app/
├── app/
│   ├── __init__.py            # App factory
│   ├── extensions.py          # Shared extension instances
│   ├── config.py              # Env-based configuration
│   ├── cli.py                 # Flask CLI commands (seed, create-admin)
│   ├── models/                # SQLAlchemy models
│   ├── blueprints/            # Feature modules
│   │   ├── auth/
│   │   ├── admin/
│   │   ├── company/
│   │   ├── member/            # Employees + individuals
│   │   ├── booking/
│   │   └── api/
│   ├── services/              # Business logic (booking, pricing, storage, billing)
│   ├── templates/
│   ├── static/
│   └── utils/
├── migrations/                # Created by `flask db init`
├── tests/
├── deploy/                    # AWS/Azure infra hints
├── .env.example
├── requirements.txt
├── wsgi.py
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Quick start (local)

Prerequisite: a running PostgreSQL 14+ instance. The fastest way is the bundled
container:

```powershell
# Start Postgres in the background
docker compose up -d db
```

Or point `DATABASE_URL` at any existing Postgres you already have.

```powershell
# 1. Create virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install deps
pip install -r requirements.txt

# 3. Copy env file and edit if needed
Copy-Item .env.example .env

# 4. Initialize DB schema
flask --app wsgi.py db init
flask --app wsgi.py db migrate -m "initial"
flask --app wsgi.py db upgrade

# 5. Seed sample data + super admin
flask --app wsgi.py seed-demo

# 6. Run
flask --app wsgi.py run --debug
```

Default super admin: `admin@coworkhub.io` / `ChangeMe123!`

## Seeded demo accounts

`flask seed-demo` creates the following accounts. **Change all passwords before
promoting this environment.**

| Role | Email | Password | Lands on | What they can do |
|------|-------|----------|----------|------------------|
| **Platform Owner** (SaaS operator) | `platform@coworkhub.io` | `ChangeMe123!` | `/platform/` | Provision and manage all tenants; suspend/reactivate; view tenant list. Does not touch per-tenant business data. |
| Super Admin (default tenant) | `admin@coworkhub.io` | `ChangeMe123!` | `/admin/` | Full access to the CoWorkHub tenant. Locations, pricing plans, staff terminations, payroll approvals, invoice voids, credit-note cancellations, refund settlements, email-template deletion. |
| CoWorkHub Manager | `manager@coworkhub.io` | `ChangeMe123!` | `/admin/` | Day-to-day operations. Companies, staff, expenses (approve/reject/pay), invoices (line items, payments), credit notes (issue), refunds (issue), booking allocations, reports. Cannot create locations, edit pricing plans, terminate staff, run/approve payroll, void invoices, or delete templates. |
| Location Manager | *(none seeded)* | — | `/admin/` | Same as Manager but scoped to a specific location. |
| Company Admin (Acme Robotics) | `jane@acme.example` | `ChangeMe123!` | `/company/` | Manage Acme's employees, subscriptions, allocations, invoices. |
| Employee (Acme Robotics) | `bob@acme.example` | `ChangeMe123!` | `/me/` | Book seats/rooms; view own bookings. |
| Individual member | `alex@example.com` | `ChangeMe123!` | `/me/` | Book seats/rooms; view own bookings. |

Sign in at `/auth/login`. New members can self-register at `/auth/register`;
companies at `/auth/register/company`. New tenants are provisioned by the
Platform Owner at `/platform/tenants/new` or from the CLI:

```powershell
flask --app wsgi.py create-tenant `
    --slug adyar-space `
    --name "Adyar Space" `
    --primary-domain adyar.example.com `
    --admin-email admin@adyar.example.com `
    --admin-password ChangeMe123!
```

## Bootstrapping configuration

These env vars control app startup (see `.env.example` for the full list):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://coworkhub:coworkhub@localhost:5432/coworkhub` | Postgres connection string. |
| `SECRET_KEY` | *(required)* | Flask session signing key. Generate a fresh one for prod. |
| `BOOTSTRAP_ADMIN_EMAIL` | `admin@coworkhub.io` | Email of the tenant Super Admin that `seed-demo` creates. |
| `BOOTSTRAP_ADMIN_PASSWORD` | `ChangeMe123!` | Password for the seeded Super Admin. |
| `DEPLOY_MODE` | `shared` | `shared` = one deployment serves many tenants (Host-based routing). `dedicated` = one tenant per deployment. |
| `TENANT_ID` | *(unset)* | Only used when `DEPLOY_MODE=dedicated` — pins this deployment to a specific tenant row. |
| `PLATFORM_BASE_DOMAIN` | `coworkhub.io` | The apex domain the Platform Owner uses (informational, for reserved-slug checks). |
| `STORAGE_BACKEND` | `local` | `local` \| `s3` \| `azure_blob` for document uploads. |
| `TIMEZONE` | `Asia/Kolkata` | Fallback timezone if the tenant's setting is missing. |
| `MAIL_*` | *(unset)* | SMTP config for outgoing email. |

Additional Platform Owner accounts can be created without running `seed-demo`:

```powershell
flask --app wsgi.py create-admin --email you@coworkhub.io --password ChangeMe123! --platform-owner
```

## Deploying to AWS

See [`deploy/aws-setup.md`](deploy/aws-setup.md) for a step-by-step production
setup guide covering VPC, security groups, RDS PostgreSQL, S3, SES, IAM
policies, EC2 with the Docker image, Route 53 + ACM, CloudWatch Logs, and
optional ALB / Auto Scaling / ECS Fargate paths.

## Hosting

**AWS (target now)**
- App: ECS Fargate or Elastic Beanstalk running the provided Dockerfile
- DB: RDS PostgreSQL
- Files: S3 bucket (see `STORAGE_BACKEND=s3`)
- Secrets: SSM Parameter Store / Secrets Manager (mapped to env vars)
- CDN: CloudFront for static assets

**Azure (future)**
- App: Azure Container Apps or App Service (same container image)
- DB: Azure Database for PostgreSQL Flexible Server
- Files: switch `STORAGE_BACKEND=azure_blob` (implementation stub included)
- Secrets: Key Vault → env vars via App Service references

The `StorageService` abstracts blob storage so switching clouds is a config change.

## Environment variables

See `.env.example` for the full list. Key ones:

| Var | Purpose |
|-----|---------|
| `FLASK_ENV` | `development` / `production` |
| `SECRET_KEY` | Flask session/CSRF key |
| `DATABASE_URL` | SQLAlchemy URI (Postgres in prod) |
| `STORAGE_BACKEND` | `s3` \| `azure_blob` \| `local` |
| `AWS_S3_BUCKET` | Document bucket |
| `AWS_REGION` | AWS region |
| `AZURE_STORAGE_CONNECTION_STRING` | For Azure mode |
| `MAIL_*` | SMTP settings |

## Roadmap / stubbed for extension

- Stripe/Razorpay integration for card payments
- SES/SendGrid transactional email
- Mobile app JWT auth (`app/blueprints/api`)
- Visitor management & QR check-in
- Slack/Teams notifications
- Occupancy heatmap analytics

## License

MIT
