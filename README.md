# Orbyn

Enterprise Asset & Resource Management System.

Orbyn centralizes how an organization tracks, allocates, books, maintains, and audits its
physical assets and shared resources — replacing spreadsheets and paper logs with structured
lifecycles, conflict-free allocation, and real-time visibility.

## Architecture note: assets as OS-managed resources

The allocation and booking engines are modeled after operating-system resource management
rather than simple CRUD:

- **Resource table.** The `Allocation` and `Booking` tables are the single source of truth for
  "who holds what right now," analogous to an OS resource-allocation table. Every grant is
  checked against this table inside one transaction before being written — never against
  in-memory or cached state.
- **Acquire / release semantics.** Allocating an asset is an *acquire*; returning it is a
  *release*. An asset can only be held by one owner at a time, the same way an OS won't hand an
  exclusively-locked resource to two processes at once.
- **No blocking deadlock — queued handoff instead.** When a second employee wants an
  already-held asset, they don't block waiting for it (which is how you get deadlocks); they
  file a `Transfer Request`, which is a queued ownership-handoff approved by an Asset Manager or
  Department Head. This avoids the classic "two holders wait on each other forever" trap.
- **Interval scheduling for bookings.** Shared/bookable resources use interval-overlap checks
  (`existing.start < new.end AND existing.end > new.start`) — the same test an OS scheduler uses
  to detect overlapping time-slice reservations on a device.
- **Background scheduler tick.** A periodic job (APScheduler) sweeps the resource tables on a
  fixed interval — like a scheduler tick — to detect overdue returns, upcoming bookings, and
  maintenance SLAs, and emits notifications. See `scheduler.py`.

## Stack

Flask, SQLAlchemy, Flask-Login, Flask-WTF, SQLite (dev), Tailwind (CDN), APScheduler.

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env
python seed.py                 # creates schema + demo data (drops existing tables)
flask run
```

Default seeded logins are printed by `seed.py` (all use password `Password123!`).

Flask-Migrate is wired up for future schema changes (`flask db migrate` / `flask db upgrade`)
once the schema stabilizes past the hackathon's initial `db.create_all()`.
