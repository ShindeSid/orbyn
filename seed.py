"""
Seed Orbyn with a larger fake dataset: 5 enterprises, 20 employees each
(100 users total), 15 assets each (75 assets total, mostly electronics).

Orbyn's data model is single-tenant (no separate "Enterprise"/"Company"
table) — each "enterprise" here is a top-level Department, since that's
the existing org-unit concept the app already has. Run with:

    python seed.py
"""
import random
from datetime import date, timedelta

from app import create_app
from extensions import db
from models import Department, AssetCategory, User, Asset

app = create_app(start_background_scheduler=False)

PASSWORD = 'Password123!'

ENTERPRISES = [
    ('Acme Manufacturing', 'acmemfg.com'),
    ('Globex Technologies', 'globextech.com'),
    ('Initech Solutions', 'initech.com'),
    ('Umbrella Logistics', 'umbrellalog.com'),
    ('Stark Industries East', 'starkeast.com'),
]

FIRST_NAMES = [
    'Aarav', 'Vivaan', 'Aditya', 'Vihaan', 'Arjun', 'Sai', 'Reyansh', 'Krishna',
    'Ishaan', 'Rohan', 'Kabir', 'Aryan', 'Dhruv', 'Rudra', 'Ayaan', 'Yash',
    'Ananya', 'Diya', 'Saanvi', 'Aadhya', 'Kiara', 'Myra', 'Anika', 'Navya',
    'Ira', 'Riya', 'Meera', 'Tara', 'Zara', 'Naina',
]
LAST_NAMES = [
    'Sharma', 'Verma', 'Gupta', 'Kapoor', 'Malhotra', 'Nair', 'Iyer', 'Rao',
    'Reddy', 'Mehta', 'Shah', 'Bose', 'Chatterjee', 'Banerjee', 'Mukherjee',
    'Iqbal', 'Khan', 'Joshi', 'Desai', 'Patel', 'Singh', 'Kaur', 'Dutta',
    'Sen', 'Menon', 'Pillai', 'Krishnan', 'Bhatt', 'Chawla', 'Ahluwalia',
]

# (name, category_key, cost_range, is_shared, weight)
ASSET_TYPES = [
    ('Laptop', 'electronics', (40000, 90000), False, 5),
    ('Desktop PC', 'electronics', (35000, 70000), False, 4),
    ('Tablet', 'electronics', (15000, 40000), False, 3),
    ('Monitor', 'electronics', (8000, 20000), False, 3),
    ('Smartphone', 'electronics', (15000, 60000), False, 2),
    ('Printer', 'electronics', (8000, 25000), True, 2),
    ('Projector', 'electronics', (20000, 60000), True, 1),
    ('Scanner', 'electronics', (5000, 15000), True, 1),
    ('External Hard Drive', 'electronics', (3000, 8000), False, 1),
    ('Webcam', 'electronics', (2000, 6000), False, 1),
    ('Network Switch', 'electronics', (10000, 30000), True, 1),
    ('Server', 'electronics', (150000, 400000), True, 1),
    ('Conference Phone', 'electronics', (15000, 40000), True, 1),
    ('Office Chair', 'furniture', (5000, 15000), False, 1),
    ('Standing Desk', 'furniture', (15000, 30000), False, 1),
]
ASSET_POOL = [t for t in ASSET_TYPES for _ in range(t[4])]


def run():
    with app.app_context():
        db.drop_all()
        db.create_all()

        electronics = AssetCategory(name='Electronics', description='Laptops, PCs, tablets, printers, and other electronics', warranty_period_days=730)
        furniture = AssetCategory(name='Furniture', description='Chairs, desks, and other furniture')
        db.session.add_all([electronics, furniture])
        db.session.flush()
        categories = {'electronics': electronics, 'furniture': furniture}

        used_emails = set()

        def unique_email(first, last, domain):
            base = f'{first.lower()}.{last.lower()}'
            email = f'{base}@{domain}'
            n = 2
            while email in used_emails:
                email = f'{base}{n}@{domain}'
                n += 1
            used_emails.add(email)
            return email

        name_pairs = [(f, l) for f in FIRST_NAMES for l in LAST_NAMES]
        random.shuffle(name_pairs)
        name_iter = iter(name_pairs)

        tag_counter = 1

        def next_tag():
            nonlocal tag_counter
            tag = f'AF-{tag_counter:04d}'
            tag_counter += 1
            return tag

        departments = []
        all_users = []
        admin_assigned = False

        for enterprise_name, domain in ENTERPRISES:
            dept = Department(name=enterprise_name, status='active')
            db.session.add(dept)
            db.session.flush()
            departments.append(dept)

            # 20 people per enterprise: 1 dept head, 2 asset managers, rest employees
            roles = ['dept_head'] + ['asset_manager'] * 2 + ['employee'] * 17
            if not admin_assigned:
                roles[3] = 'admin'  # one global admin, carved out of the first enterprise
                admin_assigned = True

            dept_users = []
            for role in roles:
                first, last = next(name_iter)
                u = User(
                    name=f'{first} {last}', email=unique_email(first, last, domain),
                    role=role, department_id=dept.id, status='active',
                )
                u.set_password(PASSWORD)
                db.session.add(u)
                dept_users.append(u)
            db.session.flush()

            dept.head_id = next(u for u in dept_users if u.role == 'dept_head').id
            all_users.extend(dept_users)

            # 15 assets per enterprise, weighted toward electronics
            for _ in range(15):
                a_name, cat_key, cost_range, shared, _weight = random.choice(ASSET_POOL)
                days_ago = random.randint(30, 1500)
                condition = random.choices(['good', 'fair', 'poor'], weights=[70, 22, 8])[0]
                asset = Asset(
                    tag=next_tag(), name=a_name, category_id=categories[cat_key].id,
                    serial_number=f'{"".join(w[0] for w in a_name.split())}-{random.randint(10000, 99999)}',
                    acquisition_date=date.today() - timedelta(days=days_ago),
                    acquisition_cost=random.randint(*cost_range),
                    condition=condition,
                    location=f'{enterprise_name} HQ, Floor {random.randint(1, 5)}',
                    is_shared=shared, status='available',
                )
                db.session.add(asset)

        db.session.commit()

        total_assets = len(ENTERPRISES) * 15
        print(f'\nSeed complete: {len(departments)} enterprises, {len(all_users)} employees, {total_assets} assets.')
        print(f'All logins use password: {PASSWORD}\n')
        for dept in departments:
            dept_users = [u for u in all_users if u.department_id == dept.id]
            print(f'--- {dept.name} ({len(dept_users)} people) ---')
            for u in dept_users:
                print(f'  {u.role:15s} {u.email}')
            print()


if __name__ == '__main__':
    run()
