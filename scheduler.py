"""
Background scheduler - the OS-style "tick" that sweeps Orbyn's resource
tables on a fixed interval, the same way an OS scheduler periodically
re-evaluates process/resource state rather than reacting only to explicit
syscalls. Each tick:

  1. Advances booking states (upcoming -> ongoing -> completed) as their
     time slices elapse.
  2. Flags overdue allocations (resource held past its expected release).
  3. Fires reminder notifications for bookings starting soon.

This keeps state fresh even when nobody is actively clicking around the app.
"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from extensions import db
from models import Allocation, Booking, Notification

TICK_INTERVAL_SECONDS = 60
REMINDER_WINDOW_MINUTES = 15


def _advance_booking_states(now):
    Booking.query.filter(
        Booking.status == 'upcoming', Booking.start_time <= now, Booking.end_time > now,
    ).update({'status': 'ongoing'}, synchronize_session=False)

    Booking.query.filter(
        Booking.status.in_(['upcoming', 'ongoing']), Booking.end_time <= now,
    ).update({'status': 'completed'}, synchronize_session=False)


def _flag_overdue_allocations(now):
    today = now.date()
    overdue = Allocation.query.filter(
        Allocation.status == 'active', Allocation.expected_return_date < today,
    ).all()
    for alloc in overdue:
        already_notified = Notification.query.filter_by(
            user_id=alloc.user_id, type='overdue_return',
            related_entity_type='allocation', related_entity_id=alloc.id,
        ).first()
        if alloc.user_id and not already_notified:
            db.session.add(Notification(
                user_id=alloc.user_id,
                message=f'Asset {alloc.asset.tag} is overdue for return (expected {alloc.expected_return_date}).',
                type='overdue_return', related_entity_type='allocation', related_entity_id=alloc.id,
            ))


def _send_booking_reminders(now):
    window_end = now + timedelta(minutes=REMINDER_WINDOW_MINUTES)
    due_soon = Booking.query.filter(
        Booking.status == 'upcoming', Booking.reminder_sent.is_(False),
        Booking.start_time > now, Booking.start_time <= window_end,
    ).all()
    for b in due_soon:
        db.session.add(Notification(
            user_id=b.user_id,
            message=f'Reminder: your booking for {b.asset.name} starts at {b.start_time.strftime("%H:%M")}.',
            type='booking_reminder', related_entity_type='booking', related_entity_id=b.id,
        ))
        b.reminder_sent = True


def tick(app):
    with app.app_context():
        now = datetime.now()
        _advance_booking_states(now)
        _flag_overdue_allocations(now)
        _send_booking_reminders(now)
        db.session.commit()


def start_scheduler(app):
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(lambda: tick(app), 'interval', seconds=TICK_INTERVAL_SECONDS, id='orbyn_scheduler_tick')
    scheduler.start()
    return scheduler
