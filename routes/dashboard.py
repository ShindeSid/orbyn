from datetime import datetime, timedelta

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from extensions import db
from models import Asset, Allocation, Booking, MaintenanceRequest

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    today = datetime.now().date()
    now = datetime.now()

    available = Asset.query.filter_by(status='available').count()
    allocated = Asset.query.filter_by(status='allocated').count()
    under_maintenance = Asset.query.filter_by(status='under_maintenance').count()

    active_bookings = Booking.query.filter(Booking.status.in_(['upcoming', 'ongoing'])).count()
    pending_transfers = Allocation.query.filter_by(status='pending_transfer').count()

    maintenance_today = MaintenanceRequest.query.filter(
        MaintenanceRequest.status.in_(['approved', 'assigned', 'in_progress']),
        db.func.date(MaintenanceRequest.created_at) == today,
    ).count()

    overdue_allocations = Allocation.query.filter(
        Allocation.status == 'active',
        Allocation.expected_return_date < today,
    ).order_by(Allocation.expected_return_date).all()

    upcoming_returns = Allocation.query.filter(
        Allocation.status == 'active',
        Allocation.expected_return_date >= today,
        Allocation.expected_return_date <= today + timedelta(days=7),
    ).order_by(Allocation.expected_return_date).all()

    upcoming_bookings = Booking.query.filter(
        Booking.status == 'upcoming', Booking.start_time >= now,
    ).order_by(Booking.start_time).limit(5).all()

    recent_activity = Allocation.query.order_by(Allocation.updated_at.desc()).limit(3).all()

    return render_template(
        'dashboard.html',
        available=available, allocated=allocated, under_maintenance=under_maintenance,
        active_bookings=active_bookings, pending_transfers=pending_transfers,
        maintenance_today=maintenance_today,
        overdue_allocations=overdue_allocations, overdue_count=len(overdue_allocations),
        upcoming_returns=upcoming_returns, upcoming_bookings=upcoming_bookings,
        today=today,
    )
