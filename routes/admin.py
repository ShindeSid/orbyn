from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import Department, AssetCategory, User, ROLES
from utils import require_role, log_activity

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# --- Tab A: Departments ---

@admin_bp.route('/departments', methods=['GET', 'POST'])
@login_required
@require_role('admin')
def departments():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        head_id = request.form.get('head_id') or None
        parent_department_id = request.form.get('parent_department_id') or None
        status = request.form.get('status', 'active')

        errors = []
        if not name:
            errors.append('Department name is required')
        elif Department.query.filter_by(name=name).first():
            errors.append('A department with this name already exists')
        if status not in ('active', 'inactive'):
            errors.append('Invalid status')

        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('admin.departments'))

        dept = Department(
            name=name,
            head_id=int(head_id) if head_id else None,
            parent_department_id=int(parent_department_id) if parent_department_id else None,
            status=status,
        )
        db.session.add(dept)
        db.session.flush()
        log_activity(current_user.id, f'Created department "{name}"', 'department', dept.id)
        db.session.commit()
        flash(f'Department "{name}" created', 'success')
        return redirect(url_for('admin.departments'))

    all_departments = Department.query.order_by(Department.name).all()
    dept_heads = User.query.filter(User.role.in_(['dept_head', 'admin'])).order_by(User.name).all()
    return render_template(
        'admin/departments.html', departments=all_departments,
        dept_heads=dept_heads, active_tab='departments',
    )


@admin_bp.route('/departments/<int:id>', methods=['POST'])
@login_required
@require_role('admin')
def edit_department(id):
    dept = Department.query.get_or_404(id)
    name = (request.form.get('name') or '').strip()
    head_id = request.form.get('head_id') or None
    parent_department_id = request.form.get('parent_department_id') or None
    status = request.form.get('status', 'active')

    errors = []
    if not name:
        errors.append('Department name is required')
    existing = Department.query.filter_by(name=name).first()
    if existing and existing.id != dept.id:
        errors.append('A department with this name already exists')
    if parent_department_id and int(parent_department_id) == dept.id:
        errors.append('A department cannot be its own parent')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('admin.departments'))

    dept.name = name
    dept.head_id = int(head_id) if head_id else None
    dept.parent_department_id = int(parent_department_id) if parent_department_id else None
    dept.status = status
    log_activity(current_user.id, f'Updated department "{name}"', 'department', dept.id)
    db.session.commit()
    flash('Department updated', 'success')
    return redirect(url_for('admin.departments'))


# --- Tab B: Asset Categories ---

@admin_bp.route('/categories', methods=['GET', 'POST'])
@login_required
@require_role('admin')
def categories():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        warranty_period_days = request.form.get('warranty_period_days') or None

        errors = []
        if not name:
            errors.append('Category name is required')
        elif AssetCategory.query.filter_by(name=name).first():
            errors.append('A category with this name already exists')
        if warranty_period_days:
            try:
                warranty_period_days = int(warranty_period_days)
                if warranty_period_days < 0:
                    errors.append('Warranty period must be a positive number of days')
            except ValueError:
                errors.append('Warranty period must be a number')

        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('admin.categories'))

        cat = AssetCategory(
            name=name, description=description or None,
            warranty_period_days=warranty_period_days or None,
        )
        db.session.add(cat)
        db.session.flush()
        log_activity(current_user.id, f'Created category "{name}"', 'category', cat.id)
        db.session.commit()
        flash(f'Category "{name}" created', 'success')
        return redirect(url_for('admin.categories'))

    all_categories = AssetCategory.query.order_by(AssetCategory.name).all()
    return render_template('admin/categories.html', categories=all_categories, active_tab='categories')


@admin_bp.route('/categories/<int:id>', methods=['POST'])
@login_required
@require_role('admin')
def edit_category(id):
    cat = AssetCategory.query.get_or_404(id)
    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    warranty_period_days = request.form.get('warranty_period_days') or None

    if not name:
        flash('Category name is required', 'error')
        return redirect(url_for('admin.categories'))

    existing = AssetCategory.query.filter_by(name=name).first()
    if existing and existing.id != cat.id:
        flash('A category with this name already exists', 'error')
        return redirect(url_for('admin.categories'))

    cat.name = name
    cat.description = description or None
    try:
        cat.warranty_period_days = int(warranty_period_days) if warranty_period_days else None
    except ValueError:
        flash('Warranty period must be a number', 'error')
        return redirect(url_for('admin.categories'))

    log_activity(current_user.id, f'Updated category "{name}"', 'category', cat.id)
    db.session.commit()
    flash('Category updated', 'success')
    return redirect(url_for('admin.categories'))


# --- Tab C: Employee Directory ---

@admin_bp.route('/employees', methods=['GET'])
@login_required
@require_role('admin')
def employees():
    all_users = User.query.order_by(User.name).all()
    all_departments = Department.query.order_by(Department.name).all()
    return render_template(
        'admin/employees.html', users=all_users, departments=all_departments,
        roles=ROLES, active_tab='employees',
    )


@admin_bp.route('/employees/<int:id>/update', methods=['POST'])
@login_required
@require_role('admin')
def update_employee(id):
    user = User.query.get_or_404(id)
    new_role = request.form.get('role')
    new_department_id = request.form.get('department_id') or None
    new_status = request.form.get('status')

    errors = []
    if new_role not in ROLES:
        errors.append('Invalid role')
    if new_status not in ('active', 'inactive'):
        errors.append('Invalid status')
    if user.id == current_user.id and new_status == 'inactive':
        errors.append('You cannot deactivate your own account')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('admin.employees'))

    old_role = user.role
    user.role = new_role
    user.department_id = int(new_department_id) if new_department_id else None
    user.status = new_status
    db.session.flush()

    if old_role != new_role:
        log_activity(
            current_user.id, f'Changed {user.name}\'s role from {old_role} to {new_role}',
            'user', user.id,
        )
        flash(f'{user.name} is now {new_role.replace("_", " ")}', 'success')
    else:
        log_activity(current_user.id, f'Updated {user.name}\'s profile', 'user', user.id)
        flash('Employee updated', 'success')

    db.session.commit()
    return redirect(url_for('admin.employees'))
