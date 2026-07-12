from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db

# --- Enum-like constants (kept as plain strings for SQLite simplicity) ---

ROLES = ['admin', 'asset_manager', 'dept_head', 'employee']
USER_STATUSES = ['active', 'inactive']
DEPT_STATUSES = ['active', 'inactive']

ASSET_STATUSES = ['available', 'allocated', 'reserved', 'under_maintenance', 'lost', 'retired', 'disposed']
ASSET_CONDITIONS = ['good', 'fair', 'poor']

ALLOCATION_STATUSES = ['active', 'pending_transfer', 'returned']

BOOKING_STATUSES = ['upcoming', 'ongoing', 'completed', 'cancelled']

MAINTENANCE_PRIORITIES = ['low', 'medium', 'high', 'critical']
MAINTENANCE_STATUSES = ['pending', 'approved', 'rejected', 'assigned', 'in_progress', 'resolved']

AUDIT_CYCLE_STATUSES = ['open', 'closed']
AUDIT_ITEM_STATUSES = ['pending', 'verified', 'missing', 'damaged']

NOTIFICATION_TYPES = [
    'asset_assigned', 'maintenance_approved', 'maintenance_rejected', 'booking_confirmed',
    'booking_cancelled', 'booking_reminder', 'transfer_requested', 'transfer_approved',
    'overdue_return', 'audit_discrepancy',
]

# --- Association table: audit cycle <-> auditors (many-to-many) ---

audit_cycle_auditors = db.Table(
    'audit_cycle_auditors',
    db.Column('audit_cycle_id', db.Integer, db.ForeignKey('audit_cycles.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
)


class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    head_id = db.Column(db.Integer, db.ForeignKey('users.id', name='fk_departments_head_id_users', use_alter=True), nullable=True)
    parent_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    status = db.Column(db.String(20), default='active', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    head = db.relationship('User', foreign_keys=[head_id], post_update=True)
    parent = db.relationship('Department', remote_side=[id], backref='sub_departments')
    employees = db.relationship('User', foreign_keys='User.department_id', back_populates='department')


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='employee', nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    status = db.Column(db.String(20), default='active', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = db.relationship('Department', foreign_keys=[department_id], back_populates='employees')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_active_user(self):
        return self.status == 'active'


class AssetCategory(db.Model):
    __tablename__ = 'asset_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.String(500))
    warranty_period_days = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assets = db.relationship('Asset', back_populates='category')


class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    tag = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('asset_categories.id'), nullable=False)
    serial_number = db.Column(db.String(100))
    acquisition_date = db.Column(db.Date, nullable=True)
    acquisition_cost = db.Column(db.Float, nullable=True)
    condition = db.Column(db.String(20), default='good')
    location = db.Column(db.String(255), nullable=False)
    photo_path = db.Column(db.String(500), nullable=True)
    is_shared = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(30), default='available', nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship('AssetCategory', back_populates='assets')
    allocations = db.relationship('Allocation', back_populates='asset', order_by='Allocation.created_at.desc()')
    bookings = db.relationship('Booking', back_populates='asset', order_by='Booking.start_time.desc()')
    maintenance_requests = db.relationship('MaintenanceRequest', back_populates='asset', order_by='MaintenanceRequest.created_at.desc()')

    @property
    def current_allocation(self):
        for a in self.allocations:
            if a.status == 'active':
                return a
        return None


class Allocation(db.Model):
    """The resource-allocation table: single source of truth for who currently holds an asset."""
    __tablename__ = 'allocations'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    dept_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    allocated_date = db.Column(db.Date, default=datetime.utcnow)
    expected_return_date = db.Column(db.Date, nullable=True)
    actual_return_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='active', index=True)  # active, pending_transfer, returned
    condition_notes = db.Column(db.String(500), nullable=True)
    transfer_to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    asset = db.relationship('Asset', back_populates='allocations')
    user = db.relationship('User', foreign_keys=[user_id])
    department = db.relationship('Department', foreign_keys=[dept_id])
    transfer_to_user = db.relationship('User', foreign_keys=[transfer_to_user_id])
    requested_by = db.relationship('User', foreign_keys=[requested_by_id])

    @property
    def holder_name(self):
        if self.user:
            return self.user.name
        if self.department:
            return self.department.name
        return '-'


class Booking(db.Model):
    """Interval-scheduling table for shared/bookable resources."""
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False)
    purpose = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='upcoming', index=True)
    reminder_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    asset = db.relationship('Asset', back_populates='bookings')
    user = db.relationship('User', foreign_keys=[user_id])


class MaintenanceRequest(db.Model):
    __tablename__ = 'maintenance_requests'
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False, index=True)
    raised_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    priority = db.Column(db.String(20), default='medium')
    photo_path = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default='pending', index=True)
    technician_name = db.Column(db.String(255), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    asset = db.relationship('Asset', back_populates='maintenance_requests')
    raised_by = db.relationship('User', foreign_keys=[raised_by_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])


class AuditCycle(db.Model):
    __tablename__ = 'audit_cycles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    scope_department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    scope_location = db.Column(db.String(255), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='open', index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

    scope_department = db.relationship('Department', foreign_keys=[scope_department_id])
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    auditors = db.relationship('User', secondary=audit_cycle_auditors, backref='audit_cycles')
    items = db.relationship('AuditItem', back_populates='cycle', order_by='AuditItem.id')

    @property
    def discrepancy_count(self):
        return sum(1 for i in self.items if i.verification_status in ('missing', 'damaged'))


class AuditItem(db.Model):
    __tablename__ = 'audit_items'
    id = db.Column(db.Integer, primary_key=True)
    audit_cycle_id = db.Column(db.Integer, db.ForeignKey('audit_cycles.id'), nullable=False, index=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('assets.id'), nullable=False)
    expected_location = db.Column(db.String(255), nullable=True)
    verification_status = db.Column(db.String(20), default='pending', index=True)
    verified_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)

    cycle = db.relationship('AuditCycle', back_populates='items')
    asset = db.relationship('Asset')
    verified_by = db.relationship('User', foreign_keys=[verified_by_id])


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id])


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    related_entity_type = db.Column(db.String(50), nullable=True)
    related_entity_id = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', foreign_keys=[user_id])
