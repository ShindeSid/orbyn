from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import AuditCycle, AuditItem, Asset, Department, User, Allocation
from utils import require_role, log_activity, notify

audit_bp = Blueprint('audit', __name__, url_prefix='/audit')


@audit_bp.route('/', methods=['GET'])
@login_required
@require_role('admin', 'asset_manager')
def list_cycles():
    cycles = AuditCycle.query.order_by(AuditCycle.created_at.desc()).all()
    return render_template('audit/list.html', cycles=cycles)


@audit_bp.route('/create', methods=['GET', 'POST'])
@login_required
@require_role('admin', 'asset_manager')
def create():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        scope_department_id = request.form.get('scope_department_id') or None
        scope_location = (request.form.get('scope_location') or '').strip()
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        auditor_ids = request.form.getlist('auditor_ids')

        errors = []
        if not name:
            errors.append('Cycle name is required')

        start_date = end_date = None
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if end_date < start_date:
                errors.append('End date must be on or after start date')
        except (ValueError, TypeError):
            errors.append('Valid start and end dates are required')

        if not auditor_ids:
            errors.append('Assign at least one auditor')
        if not scope_department_id and not scope_location:
            errors.append('Provide a department scope or a location scope')

        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('audit.create'))

        cycle = AuditCycle(
            name=name,
            scope_department_id=int(scope_department_id) if scope_department_id else None,
            scope_location=scope_location or None,
            start_date=start_date, end_date=end_date,
            status='open', created_by_id=current_user.id,
        )
        auditors = User.query.filter(User.id.in_(auditor_ids)).all()
        cycle.auditors = auditors
        db.session.add(cycle)
        db.session.flush()

        # Populate the checklist: assets matching the scope, snapshotted at creation time.
        asset_query = Asset.query.filter(Asset.status.notin_(['retired', 'disposed']))
        if scope_location:
            asset_query = asset_query.filter(Asset.location.ilike(f'%{scope_location}%'))
        matched_assets = asset_query.all()

        if scope_department_id:
            dept_id = int(scope_department_id)
            dept_asset_ids = {
                a.asset_id for a in Allocation.query.filter_by(status='active').all()
                if a.dept_id == dept_id or (a.user and a.user.department_id == dept_id)
            }
            matched_assets = [a for a in matched_assets if a.id in dept_asset_ids]

        for asset in matched_assets:
            db.session.add(AuditItem(
                audit_cycle_id=cycle.id, asset_id=asset.id,
                expected_location=asset.location, verification_status='pending',
            ))

        log_activity(current_user.id, f'Created audit cycle "{name}" ({len(matched_assets)} assets)', 'audit_cycle', cycle.id)
        for auditor in auditors:
            notify(auditor.id, f'You have been assigned to audit cycle "{name}"', 'audit_discrepancy', 'audit_cycle', cycle.id)
        db.session.commit()

        flash(f'Audit cycle "{name}" created with {len(matched_assets)} assets to verify', 'success')
        return redirect(url_for('audit.detail', id=cycle.id))

    departments = Department.query.filter_by(status='active').order_by(Department.name).all()
    auditors = User.query.filter(User.status == 'active', User.role.in_(['admin', 'asset_manager', 'dept_head', 'employee'])).order_by(User.name).all()
    return render_template('audit/create.html', departments=departments, auditors=auditors)


@audit_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    cycle = AuditCycle.query.get_or_404(id)
    is_auditor = current_user in cycle.auditors
    is_manager = current_user.role in ('admin', 'asset_manager')
    if not (is_auditor or is_manager):
        flash('You are not assigned to this audit cycle', 'error')
        return redirect(url_for('dashboard.index'))
    return render_template('audit/detail.html', cycle=cycle, can_verify=(is_auditor or is_manager) and cycle.status == 'open')


@audit_bp.route('/<int:cycle_id>/items/<int:item_id>/verify', methods=['POST'])
@login_required
def verify_item(cycle_id, item_id):
    cycle = AuditCycle.query.get_or_404(cycle_id)
    item = AuditItem.query.get_or_404(item_id)

    if cycle.status != 'open':
        flash('This audit cycle is closed', 'error')
        return redirect(url_for('audit.detail', id=cycle_id))
    if current_user not in cycle.auditors and current_user.role not in ('admin', 'asset_manager'):
        flash('You are not assigned to this audit cycle', 'error')
        return redirect(url_for('audit.detail', id=cycle_id))

    verification_status = request.form.get('verification_status')
    notes = (request.form.get('notes') or '').strip()

    if verification_status not in ('verified', 'missing', 'damaged'):
        flash('Invalid verification status', 'error')
        return redirect(url_for('audit.detail', id=cycle_id))

    item.verification_status = verification_status
    item.notes = notes or None
    item.verified_by_id = current_user.id
    item.verified_at = datetime.utcnow()
    log_activity(current_user.id, f'Marked {item.asset.tag} as {verification_status} in audit "{cycle.name}"', 'audit_item', item.id)
    db.session.commit()

    return redirect(url_for('audit.detail', id=cycle_id))


@audit_bp.route('/<int:id>/close', methods=['POST'])
@login_required
@require_role('admin', 'asset_manager')
def close_cycle(id):
    cycle = AuditCycle.query.get_or_404(id)
    if cycle.status != 'open':
        flash('This audit cycle is already closed', 'error')
        return redirect(url_for('audit.detail', id=id))

    unverified = [i for i in cycle.items if i.verification_status == 'pending']
    if unverified:
        flash(f'{len(unverified)} asset(s) still pending verification. Verify all items before closing.', 'error')
        return redirect(url_for('audit.detail', id=id))

    for item in cycle.items:
        if item.verification_status == 'missing':
            item.asset.status = 'lost'
        elif item.verification_status == 'damaged' and item.asset.status not in ('allocated',):
            item.asset.condition = 'poor'

    cycle.status = 'closed'
    cycle.closed_at = datetime.utcnow()
    log_activity(current_user.id, f'Closed audit cycle "{cycle.name}" ({cycle.discrepancy_count} discrepancies)', 'audit_cycle', cycle.id)

    if cycle.discrepancy_count:
        managers = User.query.filter(User.role.in_(['admin', 'asset_manager'])).all()
        for m in managers:
            notify(m.id, f'Audit "{cycle.name}" closed with {cycle.discrepancy_count} discrepancies', 'audit_discrepancy', 'audit_cycle', cycle.id)

    db.session.commit()
    flash(f'Audit cycle closed. {cycle.discrepancy_count} discrepancy report item(s) generated.', 'success')
    return redirect(url_for('audit.detail', id=id))
