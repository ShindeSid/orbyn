"""
Resource booking = interval scheduling over a shared device.

Two bookings on the same asset conflict if their time intervals overlap:
existing.start < new.end AND existing.end > new.start - the same interval
test an OS scheduler uses to detect clashing reservations on a device.
"""
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import Booking, Asset
from utils import log_activity, notify

bookings_bp = Blueprint('bookings', __name__, url_prefix='/bookings')


@bookings_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        asset_id = request.form.get('asset_id')
        purpose = (request.form.get('purpose') or '').strip()
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')

        errors = []
        asset = Asset.query.get(asset_id) if asset_id else None
        if not asset or not asset.is_shared:
            errors.append('Invalid or non-bookable resource')

        start = end = None
        try:
            start = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
            end = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
        except (ValueError, TypeError):
            errors.append('Invalid date/time format')

        if start and end:
            if end <= start:
                errors.append('End time must be after start time')
            if start < datetime.now():
                errors.append('Start time cannot be in the past')
            if (end - start).days > 7 or ((end - start) > timedelta(days=7)):
                errors.append('Booking duration cannot exceed 7 days')

        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('bookings.create', asset_id=asset_id))

        # --- Interval-overlap conflict check against the resource's booking table ---
        overlap = Booking.query.filter(
            Booking.asset_id == asset.id,
            Booking.start_time < end,
            Booking.end_time > start,
            Booking.status != 'cancelled',
        ).first()

        if overlap:
            flash(
                f'Time slot unavailable - {asset.name} is already booked '
                f'{overlap.start_time.strftime("%Y-%m-%d %H:%M")}–{overlap.end_time.strftime("%H:%M")}.',
                'error',
            )
            return redirect(url_for('bookings.create', asset_id=asset_id))

        booking = Booking(
            asset_id=asset.id, user_id=current_user.id,
            start_time=start, end_time=end, purpose=purpose or None,
            status='upcoming',
        )
        db.session.add(booking)
        db.session.flush()
        log_activity(current_user.id, f'Booked {asset.name} for {start.strftime("%Y-%m-%d %H:%M")}', 'booking', booking.id)
        notify(current_user.id, f'Booking confirmed: {asset.name}, {start.strftime("%Y-%m-%d %H:%M")}–{end.strftime("%H:%M")}', 'booking_confirmed', 'booking', booking.id)
        db.session.commit()

        flash(f'Booking confirmed for {asset.name}', 'success')
        return redirect(url_for('bookings.list_bookings'))

    preselect_asset_id = request.args.get('asset_id', type=int)
    assets = Asset.query.filter_by(is_shared=True).order_by(Asset.name).all()

    existing_bookings = []
    if preselect_asset_id:
        existing_bookings = Booking.query.filter(
            Booking.asset_id == preselect_asset_id,
            Booking.status.in_(['upcoming', 'ongoing']),
            Booking.end_time >= datetime.now(),
        ).order_by(Booking.start_time).all()

    return render_template(
        'bookings/create.html', assets=assets, preselect_asset_id=preselect_asset_id,
        existing_bookings=existing_bookings,
    )


@bookings_bp.route('/resource/<int:asset_id>/slots', methods=['GET'])
@login_required
def resource_slots(asset_id):
    """JSON feed of upcoming bookings for a resource, used to render the calendar."""
    bookings = Booking.query.filter(
        Booking.asset_id == asset_id,
        Booking.status.in_(['upcoming', 'ongoing']),
    ).order_by(Booking.start_time).all()
    return {
        'bookings': [
            {
                'start': b.start_time.strftime('%Y-%m-%d %H:%M'),
                'end': b.end_time.strftime('%Y-%m-%d %H:%M'),
                'by': b.user.name,
            }
            for b in bookings
        ]
    }


@bookings_bp.route('/list', methods=['GET'])
@login_required
def list_bookings():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.start_time.desc()).all()
    return render_template('bookings/list.html', bookings=bookings)


@bookings_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel(id):
    booking = Booking.query.get_or_404(id)
    if booking.user_id != current_user.id and current_user.role not in ('admin', 'asset_manager'):
        flash('You cannot cancel this booking', 'error')
        return redirect(url_for('bookings.list_bookings'))

    if booking.status == 'cancelled':
        flash('Booking is already cancelled', 'error')
        return redirect(url_for('bookings.list_bookings'))

    booking.status = 'cancelled'
    log_activity(current_user.id, f'Cancelled booking for {booking.asset.name}', 'booking', booking.id)
    notify(booking.user_id, f'Your booking for {booking.asset.name} was cancelled', 'booking_cancelled', 'booking', booking.id)
    db.session.commit()
    flash('Booking cancelled', 'success')
    return redirect(url_for('bookings.list_bookings'))
