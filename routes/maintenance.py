from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import MaintenanceRequest, Asset, User, MAINTENANCE_PRIORITIES
from utils import require_role, log_activity, notify

maintenance_bp = Blueprint('maintenance', __name__, url_prefix='/maintenance')


@maintenance_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        asset_id = request.form.get('asset_id')
        description = (request.form.get('description') or '').strip()
        priority = request.form.get('priority', 'medium')

        errors = []
        asset = Asset.query.get(asset_id) if asset_id else None
        if not asset:
            errors.append('Asset not found')
        elif asset.status in ('under_maintenance', 'retired', 'disposed'):
            errors.append(f'Asset is already {asset.status.replace("_", " ")}')
        if not description:
            errors.append('Description is required')
        elif len(description) > 500:
            errors.append('Description must be ≤500 characters')
        if priority not in MAINTENANCE_PRIORITIES:
            errors.append('Invalid priority')

        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('maintenance.create', asset_id=asset_id))

        req = MaintenanceRequest(
            asset_id=asset.id, raised_by_id=current_user.id,
            description=description, priority=priority, status='pending',
        )
        db.session.add(req)
        db.session.flush()
        log_activity(current_user.id, f'Raised maintenance request for {asset.tag}', 'maintenance', req.id)

        managers = User.query.filter(User.role.in_(['admin', 'asset_manager'])).all()
        for m in managers:
            notify(m.id, f'New maintenance request for {asset.tag} ({priority})', 'maintenance_approved', 'maintenance', req.id)
        db.session.commit()

        flash('Maintenance request submitted', 'success')
        return redirect(url_for('maintenance.detail', id=req.id))

    preselect_asset_id = request.args.get('asset_id', type=int)
    assets = Asset.query.filter(Asset.status.notin_(['under_maintenance', 'retired', 'disposed'])).order_by(Asset.tag).all()
    return render_template('maintenance/create.html', assets=assets, preselect_asset_id=preselect_asset_id, priorities=MAINTENANCE_PRIORITIES)


@maintenance_bp.route('/', methods=['GET'])
@login_required
def list_requests():
    columns = {
        'pending': [], 'approved': [], 'assigned': [], 'in_progress': [], 'resolved': [],
    }
    query = MaintenanceRequest.query
    if current_user.role not in ('admin', 'asset_manager'):
        query = query.filter_by(raised_by_id=current_user.id)

    for req in query.order_by(MaintenanceRequest.created_at.desc()).all():
        if req.status in columns:
            columns[req.status].append(req)
        elif req.status == 'rejected':
            pass  # rejected items are visible from the request's own history, not the board

    return render_template('maintenance/list.html', columns=columns)


@maintenance_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    req = MaintenanceRequest.query.get_or_404(id)
    return render_template('maintenance/detail.html', req=req)


@maintenance_bp.route('/<int:id>/decide', methods=['POST'])
@login_required
@require_role('admin', 'asset_manager')
def decide(id):
    req = MaintenanceRequest.query.get_or_404(id)
    if req.status != 'pending':
        flash('This request has already been decided', 'error')
        return redirect(url_for('maintenance.detail', id=id))

    decision = request.form.get('decision')
    reason = (request.form.get('reason') or '').strip()

    if decision == 'approve':
        req.status = 'approved'
        req.approved_by_id = current_user.id
        req.asset.status = 'under_maintenance'
        log_activity(current_user.id, f'Approved maintenance request for {req.asset.tag}', 'maintenance', req.id)
        notify(req.raised_by_id, f'Maintenance request for {req.asset.tag} approved', 'maintenance_approved', 'maintenance', req.id)
        flash('Maintenance request approved', 'success')
    elif decision == 'reject':
        req.status = 'rejected'
        req.approved_by_id = current_user.id
        req.rejection_reason = reason or None
        log_activity(current_user.id, f'Rejected maintenance request for {req.asset.tag}', 'maintenance', req.id)
        notify(req.raised_by_id, f'Maintenance request for {req.asset.tag} rejected', 'maintenance_rejected', 'maintenance', req.id)
        flash('Maintenance request rejected', 'success')
    else:
        flash('Invalid decision', 'error')
        return redirect(url_for('maintenance.detail', id=id))

    db.session.commit()
    return redirect(url_for('maintenance.detail', id=id))


@maintenance_bp.route('/<int:id>/assign', methods=['POST'])
@login_required
@require_role('admin', 'asset_manager')
def assign(id):
    req = MaintenanceRequest.query.get_or_404(id)
    if req.status != 'approved':
        flash('Request must be approved before assigning a technician', 'error')
        return redirect(url_for('maintenance.detail', id=id))

    technician_name = (request.form.get('technician_name') or '').strip()
    if not technician_name:
        flash('Technician name is required', 'error')
        return redirect(url_for('maintenance.detail', id=id))

    req.technician_name = technician_name
    req.status = 'assigned'
    log_activity(current_user.id, f'Assigned {technician_name} to {req.asset.tag}', 'maintenance', req.id)
    db.session.commit()
    flash(f'{technician_name} assigned', 'success')
    return redirect(url_for('maintenance.detail', id=id))


@maintenance_bp.route('/<int:id>/start', methods=['POST'])
@login_required
@require_role('admin', 'asset_manager')
def start(id):
    req = MaintenanceRequest.query.get_or_404(id)
    if req.status != 'assigned':
        flash('A technician must be assigned first', 'error')
        return redirect(url_for('maintenance.detail', id=id))

    req.status = 'in_progress'
    log_activity(current_user.id, f'Started work on {req.asset.tag}', 'maintenance', req.id)
    db.session.commit()
    flash('Marked as in progress', 'success')
    return redirect(url_for('maintenance.detail', id=id))


@maintenance_bp.route('/<int:id>/resolve', methods=['POST'])
@login_required
@require_role('admin', 'asset_manager')
def resolve(id):
    req = MaintenanceRequest.query.get_or_404(id)
    if req.status != 'in_progress':
        flash('Request must be in progress before it can be resolved', 'error')
        return redirect(url_for('maintenance.detail', id=id))

    req.status = 'resolved'
    req.resolved_at = datetime.utcnow()
    req.asset.status = 'available'
    log_activity(current_user.id, f'Resolved maintenance for {req.asset.tag}', 'maintenance', req.id)
    notify(req.raised_by_id, f'Maintenance for {req.asset.tag} resolved - asset is available again', 'maintenance_approved', 'maintenance', req.id)
    db.session.commit()
    flash(f'{req.asset.tag} marked available', 'success')
    return redirect(url_for('maintenance.detail', id=id))
