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

### Script (8-10 minutes)

**[OPEN LANDING PAGE]**

"Meet Orbyn. An enterprise asset and resource management system that stops organizations from losing track of what they own. Picture this: A company with 500 laptops, 20 conference rooms, 10 delivery vans, and hundreds of employees. Where's that printer your team needs? Who has the projector? When can I book the meeting room? Without Orbyn, the answers live in spreadsheets, Slack messages, and people's memory. With Orbyn, everything is tracked, allocated, and audited in real time. Let me show you how it works."

**[CLICK GET STARTED → SIGNUP with Ira Rao's account]**

"First, you sign up. Any new user starts as an Employee. Roles get promoted later by an Admin from the Employee Directory."

**[LOGGED IN - DASHBOARD]**

"Welcome to the dashboard. You can see at a glance: Total assets, how many are in use, how many are available, any under maintenance or lost, and overdue items. Now let's walk through the five core workflows that make Orbyn work."

**WORKFLOW #1: ALLOCATION (Conflict-Free)**

"[Login as Diya Dutta - Asset Manager] Diya is responsible for allocating assets. Let's give a laptop to Ira. [Click Allocate → Select Asset AF-0114 (Dell Laptop) → Select User (Ira Rao) → Submit] Notice what happened. Orbyn didn't just randomly hand out the laptop. Behind the scenes, it ran an atomic check: 'Is this laptop available right now?' If two people had tried to allocate the same laptop at the exact same time, the system would detect it and only one allocation would succeed. The other person would see 'This asset is already held by someone else. File a Transfer Request instead?' This is an OS-inspired pattern. Just like an OS won't give the same memory block to two programs, Orbyn won't hand the same asset to two people. No conflicts. No disputes."

**WORKFLOW #2: TRANSFER REQUEST (Queued Handoffs)**

"[Login as Ananya Reddy - Employee] Now Ananya also needs that laptop urgently. She can't just take it. Instead, she requests a transfer. [Click Allocate → Select same laptop → System: 'Currently held by Ira Rao. File Transfer Request?' → File Transfer Request] The system created a queued transfer. An Asset Manager has to approve it. Once approved, Ira gets a notification to return the laptop. When he does, it automatically transfers to Ananya. This avoids deadlock. Instead of people fighting over resources, we have a clear handoff queue."

**WORKFLOW #3: BOOKING (Interval-Scheduled Resources)**

"[Login as Rohan Krishnan - Employee] Rohan wants to book the conference room for a team meeting. [Click Booking → Select 'Conference Room A' → Choose Today 2 PM - 3 PM → Submit] The system checked: 'Is anyone else already booked for this time?' Using overlap-detection logic an OS scheduler uses for CPU time-slices, Orbyn blocks double-bookings automatically. If someone had booked 2:30 PM - 3:30 PM, it would say 'Not available. Try 1 PM - 2 PM instead.' No more scheduling disasters."

**WORKFLOW #4: MAINTENANCE (5-Stage Kanban)**

"[Login as Ira Rao - Employee] Ira's laptop has a broken keyboard. [Click Maintenance → Create Request → Select Asset AF-0114 → Describe 'Keyboard keys not responding' → Set Priority High → Submit] Notice the laptop's status changed to 'Under Maintenance'. It flows through five stages: Pending → Approved → Assigned → In Progress → Resolved. Each stage is clear. [Login as Diya Dutta] Diya sees the request, approves it, assigns a technician. The technician starts the repair. Once done, the laptop goes back to 'Available' and Ira gets a notification."

**WORKFLOW #5: AUDIT (Verification & Discrepancy Detection)**

"[Login as Kiara Gupta - Admin] Kiara decides to audit the Bengaluru office. [Click Audit → Create Cycle → Select Scope 'Bengaluru HQ - Engineering' → Assign Auditors] The system auto-populates every asset that's supposed to be there. Auditors physically walk through and check: 'Verified' - it's here, 'Missing' - not found, 'Damaged' - it's broken. When the cycle closes, Orbyn auto-generates a report. Missing assets are marked 'Lost', damaged assets drop to 'Poor' condition. The discrepancy report goes straight to Finance."

**BACKGROUND AUTOMATION**

"Behind the scenes, a scheduler runs continuously. Every 60 seconds in dev, or via daily cron in production, it: Advances booking states (upcoming → ongoing → completed), sends reminders 30min before meetings, flags overdue allocations, and generates alerts. All invisible automation that doesn't get in the way."

**REPORTS & ANALYTICS**

"[Click Reports] Orbyn gives you dashboards: Utilization rankings, maintenance history, department allocation summary, asset retirement warnings, booking heatmap. Everything's exportable to CSV for Finance and Compliance."

**ACTIVITY LOG**

"[Click Notifications/Activity] Every single action is logged. 'Kiara allocated AF-0114 at 2:15 PM.' 'Ira filed a transfer request at 3:30 PM.' 'Diya approved maintenance at 4:05 PM.' This is critical for compliance. If there's ever a dispute, the answer is always in the activity log."

**CLOSING**

"At its heart, Orbyn solves one problem: Organizations lose track of physical assets. Spreadsheets get out of sync. Equipment gets double-booked. Maintenance gets lost in email. Orbyn centralizes everything. Allocations are atomic - no conflicts. Bookings check for overlaps automatically. Maintenance flows through a clear kanban. Audits catch discrepancies and generate reports. The result? No more lost assets. No more double-bookings. No more equipment collecting dust because no one knew it existed. Sign up today and never lose track of an asset again."

---

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
