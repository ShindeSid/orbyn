# Orbyn

Enterprise asset & resource management system

Orbyn centralizes how an organization tracks, allocates, books, maintains, and audits its physical assets and shared resources, modeling allocation and booking as OS-style resource management - atomic conflict-free grants, queued handoffs instead of deadlocks, and interval-scheduling for bookings - replacing spreadsheets and paper logs with structured lifecycles and real-time visibility.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3 + Flask 3 |
| Templating | Jinja2 + Tailwind CSS (CDN) |
| Database | SQLite (dev) + SQLAlchemy ORM |
| Migrations | Flask-Migrate (Alembic) |
| Auth | Flask-Login (session-based) + Werkzeug password hashing |
| Forms/CSRF | Flask-WTF + WTForms + global CSRFProtect |
| Scheduler | APScheduler (background tick every 60s) |
| Frontend JS | Vanilla JS (nav toggle, form UX) - no build step |

## Quick Start

### Prerequisites
- Python 3.11+
- pip / venv

### 1. Clone and install dependencies

```bash
cd orbyn
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
# Fill in: DATABASE_URL, SECRET_KEY
```

### 3. Set up the database

```bash
python seed.py   # creates schema (db.create_all) + demo data (drops existing tables)
```

Flask-Migrate is wired up for schema changes going forward (`flask db migrate` / `flask db upgrade`) once the schema stabilizes past the initial seed.

### 4. Start the development server

```bash
flask run
```

Open http://localhost:5000 - you'll be redirected to `/auth/login`. Seeded demo logins are printed by `seed.py` (all use password `Password123!`), or create your own account via **Create an account** (always provisions as Employee - roles are promoted later by an Admin).

## Project Structure

```
orbyn/
├── app.py                   # Flask app factory, blueprint registration, scheduler startup
├── config.py                 # Env-based configuration
├── extensions.py              # SQLAlchemy, Flask-Login, Flask-Migrate instances
├── models.py                  # All 11 domain models (User, Asset, Allocation, Booking, ...)
├── forms.py                   # WTForms (Signup, Login) with validators
├── utils.py                   # require_role() RBAC decorator, log_activity(), notify()
├── scheduler.py                # APScheduler background tick (booking states, overdue, reminders)
├── seed.py                     # Demo data population script
├── routes/                    # Flask blueprints (one per feature area)
│   ├── auth.py                 # Signup, login, logout
│   ├── admin.py                 # Departments, categories, employee directory + role promotion
│   ├── assets.py                 # Register, list, detail, retire
│   ├── allocations.py             # Allocate, transfer request/approve, return
│   ├── bookings.py                 # Create, list, cancel, availability API
│   ├── maintenance.py               # Create, list (kanban), detail, workflow actions
│   ├── audit.py                      # Cycle create, verify, close + discrepancy detection
│   ├── dashboard.py                   # KPI dashboard
│   ├── reports.py                      # Analytics + CSV export
│   └── notifications.py                 # Notification feed + activity log
├── templates/                  # Jinja2 templates, organized by feature
│   ├── base.html                # Responsive nav shell, flash messages
│   ├── auth/, admin/, assets/, allocations/, bookings/, maintenance/, audit/, reports/, notifications/
│   └── dashboard.html
└── static/
    └── main.js                  # Nav toggle, form UX helpers
```

## User Roles

| Role | Capabilities |
|---|---|
| ADMIN | Full access: org setup, role promotion, asset registration, all allocations/audits/reports |
| ASSET_MANAGER | Register assets, allocate/transfer/return, run maintenance & audit workflows |
| DEPT_HEAD | Approve transfers for their department, view department reports |
| EMPLOYEE | Submit maintenance requests, book shared resources, view own allocations/bookings |

Signup always creates an **Employee** account - roles are only ever promoted by an Admin from the Employee Directory, never self-assigned.

## Key Features

### OS-Inspired Allocation Engine
The `Allocation` table is the single source of truth for "who holds what right now" - every grant is re-checked atomically (`db.session.refresh`) inside one transaction immediately before writing, so two simultaneous requests for the same asset can't both succeed. A second requester sees "already held by X" and can only file a **Transfer Request** - a queued ownership handoff approved by an Asset Manager/Dept Head - rather than blocking indefinitely (avoiding deadlock).

### Interval-Scheduled Booking
Shared/bookable resources use interval-overlap checks (`existing.start < new.end AND existing.end > new.start`) - the same test an OS scheduler uses to detect clashing time-slice reservations. A booking starting exactly when another ends is correctly allowed.

### Maintenance Workflow
Requests move through a 5-state kanban: **Pending → Approved/Rejected → Assigned → In Progress → Resolved**. The asset auto-flips to `under_maintenance` on approval and back to `available` on resolution.

### Audit Cycles
Create a cycle scoped to a department/location, auto-populate its asset checklist, and verify each item as Verified/Missing/Damaged. Closing a cycle auto-detects discrepancies - confirmed-missing assets flip to `lost`, damaged assets drop to `poor` condition - and generates a discrepancy report.

### Background Scheduler
An APScheduler tick runs every 60 seconds to advance booking states (`upcoming → ongoing → completed`), flag overdue allocations, and send booking reminders - decoupling state transitions from user actions.

### Reports & Activity
Utilization ranking, maintenance frequency by category, department allocation summary, assets nearing retirement, warranty expiry warnings, a booking heatmap by hour, and full CSV export. Every action (allocate, approve, verify, close cycle, etc.) is logged to an audit-friendly activity feed.

## Routes

### Auth
- `GET/POST /auth/signup` - Create account (always Employee role)
- `GET/POST /auth/login` - Login
- `GET /auth/logout` - Logout

### Org Setup (Admin)
- `GET/POST /admin/departments` - List + create departments
- `POST /admin/departments/<id>/edit` - Update department
- `GET/POST /admin/categories` - List + create asset categories
- `POST /admin/categories/<id>/edit` - Update category
- `GET /admin/employees` - Employee directory
- `POST /admin/employees/<id>/update` - Update role/department/status

### Assets
- `GET/POST /assets/register` - Register asset (auto-tagged `AF-####`)
- `GET /assets/` - Directory with search/filter
- `GET /assets/<id>` - Detail + allocation/maintenance/booking history
- `POST /assets/<id>/retire` - Retire asset

### Allocations
- `GET/POST /allocations/create` - Allocate to user/department
- `POST /allocations/<id>/transfer_request` - File a transfer request
- `GET /allocations/transfers` - Pending transfer approvals
- `POST /allocations/<id>/transfer_approve` - Approve/reject transfer
- `GET/POST /allocations/<id>/return` - Return asset with condition notes

### Bookings
- `GET/POST /bookings/create` - Book a shared resource
- `GET /bookings/list` - My bookings
- `POST /bookings/<id>/cancel` - Cancel booking
- `GET /bookings/resource/<id>/slots` - Availability JSON (async)

### Maintenance
- `GET/POST /maintenance/create` - Raise request
- `GET /maintenance/` - Kanban board
- `GET /maintenance/<id>` - Detail + workflow actions
- `POST /maintenance/<id>/decide` - Approve/reject
- `POST /maintenance/<id>/assign` - Assign technician
- `POST /maintenance/<id>/start` - Mark in progress
- `POST /maintenance/<id>/resolve` - Mark resolved

### Audit
- `GET /audit/` - Cycles list
- `GET/POST /audit/create` - Create cycle with scope + auditors
- `GET /audit/<id>` - Verification checklist
- `POST /audit/<cycle_id>/verify/<item_id>` - Verify item
- `POST /audit/<id>/close` - Close cycle + generate discrepancy report

### Dashboard, Reports & Notifications
- `GET /dashboard` - KPI cards, overdue alerts, upcoming returns/bookings
- `GET /reports/` - Analytics dashboard
- `GET /reports/export.csv` - Full asset inventory export
- `GET /notifications/` - Filterable notification feed + activity log (Admin)

## Environment Variables

```
DATABASE_URL=sqlite:///orbyn.db
SECRET_KEY=your-secret-key
```

## System Flowchart

### Core Workflows

**1. Asset Allocation (Conflict-Free)**
```
Select Asset → Select User → [ATOMIC CHECK]
                              ├─ Available? → Allocate (asset status = in_use)
                              └─ Held by X? → Suggest Transfer Request
```

**2. Transfer Request (Queued Handoffs)**
```
Employee wants asset held by another → File Transfer Request
  → Asset Manager reviews & approves
    → Current holder notified to return
      → On return → Auto-allocate to requester
```

**3. Booking (Interval-Scheduled Resources)**
```
Select Resource → Choose Time Slot → [OVERLAP CHECK]
                                      ├─ No conflict? → Booking created (state: upcoming)
                                      └─ Conflict? → Reject, suggest alternate slot
                                      
Background Scheduler (every 60s):
  upcoming → ongoing (when start_time reached)
  ongoing → completed (when end_time passed)
  Send reminders 30min before start
```

**4. Maintenance (5-Stage Kanban)**
```
Submit Request → Pending
  → Asset Manager Approves → asset.status = under_maintenance
    → Assigned → Technician assigned
      → In Progress → Repair underway
        → Resolved → asset.status = available (notify requester)
```

**5. Audit (Verification & Discrepancy Detection)**
```
Create Audit Cycle (scoped to department/location)
  → Auto-populate assets in scope
    → Auditors verify: Verified / Missing / Damaged
      → Close Cycle
        → Auto-detect: Missing → lost, Damaged → poor condition
          → Generate Discrepancy Report (compliance trail)
```

### Background Scheduler (Every 60 seconds)
- Advance booking states (upcoming → ongoing → completed)
- Flag overdue allocations (return past due date)
- Send booking reminders (30min before start)
- Prepare maintenance frequency reports

### Data Persistence
- **Activity Log**: Every action timestamped (allocate, approve, verify, return, etc.)
- **Notifications**: Real-time alerts to stakeholders
- **Audit Trail**: Full compliance record for disputes & investigations

---

## Demo Video Script

### Setup: Demo Accounts

10 demo users across 4 roles, 4 enterprises. All use password: `Password123!`

| # | Role | Enterprise | Name | Email |
|---|---|---|---|---|
| 1 | Admin | Acme Manufacturing | Kiara Gupta | kiara.gupta@acmemfg.com |
| 2 | Asset Manager | Acme Manufacturing | Diya Dutta | diya.dutta@acmemfg.com |
| 3 | Dept Head | Acme Manufacturing | Diya Bose | diya.bose@acmemfg.com |
| 4 | Employee | Acme Manufacturing | Ira Rao | ira.rao@acmemfg.com |
| 5 | Asset Manager | Globex Technologies | Sai Joshi | sai.joshi@globextech.com |
| 6 | Dept Head | Globex Technologies | Ananya Chatterjee | ananya.chatterjee@globextech.com |
| 7 | Employee | Globex Technologies | Ananya Reddy | ananya.reddy@globextech.com |
| 8 | Dept Head | Initech Solutions | Rohan Mukherjee | rohan.mukherjee@initech.com |
| 9 | Employee | Initech Solutions | Zara Mukherjee | zara.mukherjee@initech.com |
| 10 | Employee | Umbrella Logistics | Rohan Krishnan | rohan.krishnan@umbrellalog.com |

## Color Design System

| Token | Value | Usage |
|---|---|---|
| Brand 700 | `#0e7490` | Nav bar (teal) |
| Brand 600 | `#0891b2` | Buttons, links, active states (cyan) |
| Brand 500 | `#06b6d4` | Focus rings, accents (light cyan) |
| Brand 100 | `#cffafe` | Subtle highlights |
| Brand 50 | `#ecfeff` | Hover backgrounds (very light cyan) |
| Success | Tailwind `green-600` | Approved, verified, available states |
| Warning | Tailwind `amber-600` | Under maintenance, pending states |
| Danger | Tailwind `red-600` | Overdue, rejected, lost/damaged states |
| Surface | Tailwind `gray-50` | Page background |
| Text | Tailwind `gray-900` | Primary text |

## Production Deployment

```bash
pip install -r requirements.txt
flask db upgrade      # apply migrations instead of seed.py's db.create_all()
gunicorn app:app       # or another production WSGI server
```

For production, ensure:
- Set a strong random `SECRET_KEY`
- Point `DATABASE_URL` at a production database (e.g. PostgreSQL) instead of SQLite
- Serve `static/` via a reverse proxy / CDN rather than Flask's dev static handler
- Run the background scheduler in exactly one process (see the `WERKZEUG_RUN_MAIN` guard in `app.py`) - don't run multiple gunicorn workers with `start_background_scheduler=True` in each
