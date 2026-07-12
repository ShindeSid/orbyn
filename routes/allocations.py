"""
Allocation & Transfer engine.

Modeled after OS resource management: the `allocations` table is the single
resource-allocation table. Allocating is an *acquire*, returning is a
*release*, and an asset (the resource) can only be held by one owner at a
time. Rather than letting a second requester block indefinitely waiting on a
held resource (the classic setup for deadlock), they file a Transfer
Request - a queued ownership handoff that an Asset Manager / Department Head
approves, so the resource table never has two active holders for one asset.
"""
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import Asset, Allocation, User, Department
from utils import require_role, log_activity, notify

alloc_bp = Blueprint('allocations', __name__, url_prefix='/allocations')


@alloc_bp.route('/create', methods=['GET', 'POST'])
@login_required
@require_role('admin', 'asset_manager', 'dept_head')
def create():
    if request.method == 'POST':
        asset_id = request.form.get('asset_id')
        user_id = request.form.get('user_id') or None
        dept_id = request.form.get('dept_id') or None
        expected_return_date = request.form.get('expected_return_date')

        errors = []
        asset = Asset.query.get(asset_id) if asset_id else None
        if not asset:
            errors.append('Asset not found')

        ret_date = None
        if not expected_return_date:
            errors.append('Expected return date is required')
        else:
            try:
                ret_date = datetime.strptime(expected_return_date, '%Y-%m-%d').date()
                if ret_date <= datetime.now().date():
                    errors.append('Expected return date must be in the future')
                if (ret_date - datetime.now().date()).days > 365:
                    errors.append('Expected return date cannot be more than 1 year away')
            except ValueError:
                errors.append('Invalid date format')

        if not user_id and not dept_id:
            errors.append('Select either an employee or a department')
        if user_id and dept_id:
            errors.append('Select either an employee or a department, not both')

        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('allocations.create', asset_id=asset_id))

        # --- Acquire: single atomic check-then-write against the resource table ---
        # Re-check status right before the write (not from any cached page state)
        # so two near-simultaneous requests can't both see "available".
        db.session.refresh(asset)
        existing = Allocation.query.filter_by(asset_id=asset.id, status='active').first()
        if asset.status != 'available' or existing:
            holder = existing.holder_name if existing else 'someone else'
            flash(f'Asset {asset.tag} is already held by {holder}. Use a Transfer Request instead.', 'error')
            return redirect(url_for('assets.detail', id=asset.id))

        allocation = Allocation(
            asset_id=asset.id,
            user_id=int(user_id) if user_id else None,
            dept_id=int(dept_id) if dept_id else None,
            expected_return_date=ret_date,
            status='active',
        )
        asset.status = 'allocated'
        db.session.add(allocation)
        db.session.flush()

        log_activity(current_user.id, f'Allocated {asset.tag} to {allocation.holder_name}', 'allocation', allocation.id)
        if user_id:
            notify(int(user_id), f'Asset {asset.tag} ({asset.name}) has been assigned to you', 'asset_assigned', 'asset', asset.id)
        db.session.commit()

        flash(f'Asset {asset.tag} allocated to {allocation.holder_name}', 'success')
        return redirect(url_for('assets.detail', id=asset.id))

    preselect_asset_id = request.args.get('asset_id', type=int)
    assets = Asset.query.filter_by(status='available').order_by(Asset.tag).all()
    users = User.query.filter_by(status='active').order_by(User.name).all()
    departments = Department.query.filter_by(status='active').order_by(Department.name).all()

    return render_template(
        'allocations/create.html', assets=assets, users=users, departments=departments,
        preselect_asset_id=preselect_asset_id,
    )


@alloc_bp.route('/<int:id>/transfer-request', methods=['POST'])
@login_required
def transfer_request(id):
    allocation = Allocation.query.get_or_404(id)
    new_user_id = request.form.get('new_user_id')

    is_holder = allocation.user_id == current_user.id
    is_manager = current_user.role in ('admin', 'asset_manager', 'dept_head')
    if not (is_holder or is_manager):
        flash('You are not authorized to request a transfer for this allocation', 'error')
        return redirect(url_for('assets.detail', id=allocation.asset_id))

    if allocation.status != 'active':
        flash('This allocation is not currently active', 'error')
        return redirect(url_for('assets.detail', id=allocation.asset_id))

    if not new_user_id:
        flash('Select a new holder', 'error')
        return redirect(url_for('assets.detail', id=allocation.asset_id))

    if int(new_user_id) == allocation.user_id:
        flash('Asset is already held by this employee', 'error')
        return redirect(url_for('assets.detail', id=allocation.asset_id))

    allocation.status = 'pending_transfer'
    allocation.transfer_to_user_id = int(new_user_id)
    allocation.requested_by_id = current_user.id
    db.session.flush()

    new_holder = User.query.get(new_user_id)
    log_activity(current_user.id, f'Requested transfer of {allocation.asset.tag} to {new_holder.name}', 'allocation', allocation.id)

    approvers = User.query.filter(User.role.in_(['admin', 'asset_manager'])).all()
    for approver in approvers:
        notify(approver.id, f'Transfer request: {allocation.asset.tag} to {new_holder.name}', 'transfer_requested', 'allocation', allocation.id)

    db.session.commit()
    flash('Transfer request submitted for approval', 'success')
    return redirect(url_for('assets.detail', id=allocation.asset_id))


@alloc_bp.route('/transfers', methods=['GET'])
@login_required
@require_role('admin', 'asset_manager', 'dept_head')
def transfers():
    pending = Allocation.query.filter_by(status='pending_transfer').order_by(Allocation.updated_at.desc()).all()
    return render_template('allocations/transfers.html', pending=pending)


@alloc_bp.route('/<int:id>/transfer-approve', methods=['POST'])
@login_required
@require_role('admin', 'asset_manager', 'dept_head')
def transfer_approve(id):
    allocation = Allocation.query.get_or_404(id)
    if allocation.status != 'pending_transfer':
        flash('This allocation is not pending transfer', 'error')
        return redirect(url_for('allocations.transfers'))

    approve = request.form.get('decision') == 'approve'
    asset = allocation.asset

    if approve:
        allocation.status = 'returned'
        allocation.actual_return_date = datetime.now().date()

        new_allocation = Allocation(
            asset_id=asset.id,
            user_id=allocation.transfer_to_user_id,
            expected_return_date=allocation.expected_return_date,
            status='active',
        )
        db.session.add(new_allocation)
        db.session.flush()

        log_activity(current_user.id, f'Approved transfer of {asset.tag} to {new_allocation.holder_name}', 'allocation', new_allocation.id)
        notify(allocation.transfer_to_user_id, f'Asset {asset.tag} has been transferred to you', 'transfer_approved', 'asset', asset.id)
        flash(f'Transfer approved. {asset.tag} is now held by {new_allocation.holder_name}.', 'success')
    else:
        allocation.status = 'active'
        allocation.transfer_to_user_id = None
        log_activity(current_user.id, f'Rejected transfer request for {asset.tag}', 'allocation', allocation.id)
        flash('Transfer request rejected', 'success')

    db.session.commit()
    return redirect(url_for('allocations.transfers'))


@alloc_bp.route('/<int:id>/return', methods=['GET', 'POST'])
@login_required
def return_asset(id):
    allocation = Allocation.query.get_or_404(id)
    asset = allocation.asset

    is_holder = allocation.user_id == current_user.id
    is_manager = current_user.role in ('admin', 'asset_manager', 'dept_head')
    if not (is_holder or is_manager):
        flash('You are not authorized to return this asset', 'error')
        return redirect(url_for('assets.detail', id=asset.id))

    if allocation.status != 'active':
        flash('This allocation is not active', 'error')
        return redirect(url_for('assets.detail', id=asset.id))

    if request.method == 'POST':
        condition_notes = (request.form.get('condition_notes') or '').strip()
        if len(condition_notes) > 500:
            flash('Notes must be ≤500 characters', 'error')
            return redirect(url_for('allocations.return_asset', id=id))

        allocation.status = 'returned'
        allocation.actual_return_date = datetime.now().date()
        allocation.condition_notes = condition_notes or None
        asset.status = 'available'

        log_activity(current_user.id, f'Returned asset {asset.tag}', 'allocation', allocation.id)
        db.session.commit()
        flash(f'Asset {asset.tag} returned and marked available', 'success')
        return redirect(url_for('assets.detail', id=asset.id))

    return render_template('allocations/return.html', allocation=allocation, asset=asset)
