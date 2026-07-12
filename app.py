import os

from flask import Flask, redirect, url_for
from flask_login import current_user
from flask_wtf import CSRFProtect
from datetime import datetime

from config import Config
from extensions import db, login_manager, migrate

csrf = CSRFProtect()


def create_app(start_background_scheduler=True):
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'error'

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.assets import assets_bp
    from routes.allocations import alloc_bp
    from routes.bookings import bookings_bp
    from routes.maintenance import maintenance_bp
    from routes.audit import audit_bp
    from routes.dashboard import dashboard_bp
    from routes.reports import reports_bp
    from routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(alloc_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(notifications_bp)

    @app.route('/')
    def home():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))

    @app.context_processor
    def inject_globals():
        unread_count = 0
        if current_user.is_authenticated:
            from models import Notification
            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return dict(unread_count=unread_count, now=datetime.utcnow)

    # Only start the tick loop in the actual serving process — under the
    # Werkzeug debug reloader, the parent process re-execs a child with
    # WERKZEUG_RUN_MAIN=true, and we don't want two scheduler threads
    # ticking against the same DB.
    if start_background_scheduler and (os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug):
        from scheduler import start_scheduler
        start_scheduler(app)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
