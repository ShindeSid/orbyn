from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user

from extensions import db
from models import Notification, ActivityLog
from utils import require_role

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

TYPE_GROUPS = {
    'alerts': ['overdue_return', 'audit_discrepancy', 'asset_assigned'],
    'approvals': ['transfer_requested', 'transfer_approved', 'maintenance_approved', 'maintenance_rejected'],
    'bookings': ['booking_confirmed', 'booking_cancelled', 'booking_reminder'],
}


@notifications_bp.route('/', methods=['GET'])
@login_required
def index():
    tab = request.args.get('tab', 'all')
    query = Notification.query.filter_by(user_id=current_user.id)

    if tab in TYPE_GROUPS:
        query = query.filter(Notification.type.in_(TYPE_GROUPS[tab]))

    notifications = query.order_by(Notification.created_at.desc()).limit(50).all()

    unread_ids = [n.id for n in notifications if not n.is_read]
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update({'is_read': True}, synchronize_session=False)
        db.session.commit()

    activity_log = None
    if current_user.role in ('admin', 'asset_manager'):
        activity_log = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(50).all()

    return render_template('notifications/index.html', notifications=notifications, tab=tab, activity_log=activity_log)
