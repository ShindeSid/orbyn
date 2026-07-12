from functools import wraps
from flask import redirect, flash, url_for
from flask_login import current_user
from extensions import db
from models import ActivityLog, Notification


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_activity(user_id, action, entity_type=None, entity_id=None, details=None):
    entry = ActivityLog(
        user_id=user_id, action=action, entity_type=entity_type,
        entity_id=entity_id, details=details,
    )
    db.session.add(entry)


def notify(user_id, message, type, related_entity_type=None, related_entity_id=None):
    if not user_id:
        return
    n = Notification(
        user_id=user_id, message=message, type=type,
        related_entity_type=related_entity_type, related_entity_id=related_entity_id,
    )
    db.session.add(n)
