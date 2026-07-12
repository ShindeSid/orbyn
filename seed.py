"""Seed Orbyn with realistic demo data. Run with: python seed.py"""
from datetime import date, datetime, timedelta

from app import create_app
from extensions import db
from models import (
    Department, AssetCategory, User, Asset, Allocation, Booking,
    MaintenanceRequest, AuditCycle, AuditItem, Notification,
)

app = create_app(start_background_scheduler=False)


def run():
    with app.app_context():
        db.drop_all()
        db.create_all()

        # --- Departments ---
        engineering = Department(name='Engineering', status='active')
        facilities = Department(name='Facilities', status='active')
        field_ops = Department(name='Field Ops (east)', status='inactive')
        sales = Department(name='Sales', status='active')
        db.session.add_all([engineering, facilities, field_ops, sales])
        db.session.flush()

        # --- Categories ---
        electronics = AssetCategory(name='Electronics', description='Laptops, monitors, projectors', warranty_period_days=730)
        furniture = AssetCategory(name='Furniture', description='Chairs, desks, cabinets')
        vehicles = AssetCategory(name='Vehicles', description='Vans, forklifts', warranty_period_days=365)
        db.session.add_all([electronics, furniture, vehicles])
        db.session.flush()

        # --- Users ---
        def make_user(name, email, role, department=None, status='active'):
            u = User(name=name, email=email, role=role, status=status,
                      department_id=department.id if department else None)
            u.set_password('Password123!')
            db.session.add(u)
            return u

        admin = make_user('Admin User', 'admin@orbyn.app', 'admin')
        asset_mgr = make_user('Karan Bose', 'karan.bose@orbyn.app', 'asset_manager')
        dept_head_eng = make_user('Aditi Rao', 'aditi.rao@orbyn.app', 'dept_head', engineering)
        dept_head_facilities = make_user('Rohan Mehta', 'rohan.mehta@orbyn.app', 'dept_head', facilities)
        dept_head_field_ops = make_user('Sana Iqbal', 'sana.iqbal@orbyn.app', 'dept_head', field_ops)
        priya = make_user('Priya Shah', 'priya.shah@orbyn.app', 'employee', engineering)
        raj = make_user('Raj Kapoor', 'raj.kapoor@orbyn.app', 'employee', engineering)
        arjun = make_user('Arjun Nair', 'arjun.nair@orbyn.app', 'employee', facilities)
        neha = make_user('Neha Verma', 'neha.verma@orbyn.app', 'employee', sales)
        db.session.flush()

        engineering.head_id = dept_head_eng.id
        facilities.head_id = dept_head_facilities.id
        field_ops.head_id = dept_head_field_ops.id

        # --- Assets ---
        def make_asset(tag, name, category, location, status='available', is_shared=False,
                        serial=None, condition='good', acquired_days_ago=200, cost=None):
            a = Asset(
                tag=tag, name=name, category_id=category.id, location=location,
                status=status, is_shared=is_shared, serial_number=serial, condition=condition,
                acquisition_date=date.today() - timedelta(days=acquired_days_ago),
                acquisition_cost=cost,
            )
            db.session.add(a)
            return a

        laptop_114 = make_asset('AF-0114', 'Dell Laptop', electronics, 'Bengaluru HQ, Floor 2', status='allocated', serial='DL-99231', acquired_days_ago=400, cost=85000)
        laptop_003 = make_asset('AF-0003', 'Dell Laptop', electronics, 'Bengaluru HQ, Floor 3', status='available', serial='DL-88120', acquired_days_ago=1600, cost=72000)
        projector = make_asset('AF-0062', 'Projector', electronics, 'HQ Floor 2', status='under_maintenance', is_shared=True, acquired_days_ago=900, cost=45000)
        chair_201 = make_asset('AF-0201', 'Office Chair', furniture, 'Warehouse', status='available', acquired_days_ago=100, cost=6000)
        chair_9921 = make_asset('AF-9921', 'Office Chair', furniture, 'Desk E14', status='lost', acquired_days_ago=500, cost=5500)
        monitor = make_asset('AF-9838', 'Monitor', electronics, 'Desk E15', status='available', condition='poor', acquired_days_ago=1500, cost=15000)
        room_b2 = make_asset('AF-B002', 'Conference Room B2', furniture, 'HQ Floor 2', status='available', is_shared=True, acquired_days_ago=1000)
        van_393 = make_asset('AF-0393', 'Delivery Van', vehicles, 'Field Depot', status='available', is_shared=True, acquired_days_ago=300, cost=1200000)
        forklift = make_asset('AF-0087', 'Forklift', vehicles, 'Warehouse', status='available', acquired_days_ago=1450, cost=900000)
        camera = make_asset('AF-0301', 'Camera', electronics, 'Storage Room', status='available', acquired_days_ago=700, cost=55000)
        db.session.flush()

        # --- Allocations ---
        alloc_priya = Allocation(
            asset_id=laptop_114.id, user_id=priya.id, status='active',
            allocated_date=date.today() - timedelta(days=60),
            expected_return_date=date.today() + timedelta(days=30),
        )
        alloc_arjun_overdue = Allocation(
            asset_id=chair_201.id, user_id=arjun.id, status='returned',
            allocated_date=date.today() - timedelta(days=200),
            expected_return_date=date.today() - timedelta(days=100),
            actual_return_date=date.today() - timedelta(days=90),
        )
        # a currently overdue active allocation, to populate the dashboard alert
        chair_201.status = 'allocated'
        alloc_overdue_active = Allocation(
            asset_id=chair_201.id, user_id=neha.id, status='active',
            allocated_date=date.today() - timedelta(days=40),
            expected_return_date=date.today() - timedelta(days=3),
        )
        db.session.add_all([alloc_priya, alloc_arjun_overdue, alloc_overdue_active])
        db.session.flush()

        # --- Bookings ---
        today_9am = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
        booking1 = Booking(
            asset_id=room_b2.id, user_id=raj.id,
            start_time=today_9am, end_time=today_9am + timedelta(hours=1),
            status='upcoming', purpose='Procurement sync',
        )
        van_start = (datetime.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        booking2 = Booking(
            asset_id=van_393.id, user_id=arjun.id,
            start_time=van_start, end_time=van_start + timedelta(hours=3),
            status='upcoming', purpose='Site delivery',
        )
        db.session.add_all([booking1, booking2])
        db.session.flush()

        # --- Maintenance requests (populate every kanban column) ---
        m_pending = MaintenanceRequest(
            asset_id=monitor.id, raised_by_id=priya.id,
            description='Monitor flickers intermittently, especially on startup.',
            priority='medium', status='pending',
        )
        m_approved = MaintenanceRequest(
            asset_id=projector.id, raised_by_id=raj.id,
            description='Projector bulb not turning on.',
            priority='high', status='approved', approved_by_id=asset_mgr.id,
        )
        m_assigned = MaintenanceRequest(
            asset_id=forklift.id, raised_by_id=arjun.id,
            description='AC unit making a loud noise, needs inspection.',
            priority='medium', status='assigned', approved_by_id=asset_mgr.id,
            technician_name='Tech R. Varma',
        )
        m_in_progress = MaintenanceRequest(
            asset_id=van_393.id, raised_by_id=neha.id,
            description='Forklift hydraulics leaking fluid.',
            priority='critical', status='in_progress', approved_by_id=asset_mgr.id,
            technician_name='Tech S. Nair',
        )
        m_resolved = MaintenanceRequest(
            asset_id=chair_9921.id, raised_by_id=priya.id,
            description='Chair repair — wheel replacement.',
            priority='low', status='resolved', approved_by_id=asset_mgr.id,
            technician_name='Tech A. Joshi', resolved_at=datetime.utcnow() - timedelta(days=5),
        )
        db.session.add_all([m_pending, m_approved, m_assigned, m_in_progress, m_resolved])
        db.session.flush()

        # --- Audit cycle ---
        cycle = AuditCycle(
            name='Q3 audit: Engineering dept', scope_department_id=engineering.id,
            start_date=date.today() - timedelta(days=5), end_date=date.today() + timedelta(days=5),
            status='open', created_by_id=admin.id,
        )
        cycle.auditors = [asset_mgr, dept_head_eng]
        db.session.add(cycle)
        db.session.flush()

        db.session.add_all([
            AuditItem(audit_cycle_id=cycle.id, asset_id=laptop_003.id, expected_location='Desk E12', verification_status='verified', verified_by_id=asset_mgr.id, verified_at=datetime.utcnow()),
            AuditItem(audit_cycle_id=cycle.id, asset_id=chair_9921.id, expected_location='Desk E14', verification_status='missing', verified_by_id=asset_mgr.id, verified_at=datetime.utcnow(), notes='Not found at desk'),
            AuditItem(audit_cycle_id=cycle.id, asset_id=monitor.id, expected_location='Desk E15', verification_status='damaged', verified_by_id=asset_mgr.id, verified_at=datetime.utcnow(), notes='Cracked bezel'),
            AuditItem(audit_cycle_id=cycle.id, asset_id=laptop_114.id, expected_location='Floor 2', verification_status='pending'),
        ])

        # --- A few notifications so the bell/activity feed isn't empty ---
        db.session.add_all([
            Notification(user_id=priya.id, message=f'Asset {laptop_114.tag} assigned to you', type='asset_assigned', related_entity_type='asset', related_entity_id=laptop_114.id),
            Notification(user_id=asset_mgr.id, message='Maintenance request AF-0055 approved', type='maintenance_approved'),
            Notification(user_id=raj.id, message='Booking confirmed: Room B2, 09:00–10:00', type='booking_confirmed', related_entity_type='booking', related_entity_id=booking1.id),
            Notification(user_id=asset_mgr.id, message='Audit discrepancy flagged: AF-9921 missing', type='audit_discrepancy', related_entity_type='audit_cycle', related_entity_id=cycle.id),
        ])

        db.session.commit()

        print('\nSeed complete. Demo logins (password: Password123!):\n')
        print(f'  Admin           {admin.email}')
        print(f'  Asset Manager   {asset_mgr.email}')
        print(f'  Dept Head       {dept_head_eng.email}')
        print(f'  Dept Head       {dept_head_facilities.email}')
        print(f'  Employee        {priya.email}')
        print(f'  Employee        {raj.email}')
        print(f'  Employee        {arjun.email}')
        print(f'  Employee        {neha.email}\n')


if __name__ == '__main__':
    run()
