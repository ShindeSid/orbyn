from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from extensions import db
from models import Asset, AssetCategory, Department, User, ASSET_STATUSES, ASSET_CONDITIONS
from utils import require_role, log_activity

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')


def generate_asset_tag():
    last_asset = Asset.query.order_by(Asset.id.desc()).first()
    next_num = (last_asset.id + 1) if last_asset else 1
    tag = f'AF-{next_num:04d}'
    # Guard against tag collisions from deleted rows.
    while Asset.query.filter_by(tag=tag).first():
        next_num += 1
        tag = f'AF-{next_num:04d}'
    return tag


@assets_bp.route('/register', methods=['GET', 'POST'])
@login_required
@require_role('admin', 'asset_manager')
def register():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        category_id = request.form.get('category_id')
        serial_number = (request.form.get('serial_number') or '').strip()
        acquisition_date = request.form.get('acquisition_date') or None
        acquisition_cost = request.form.get('acquisition_cost') or None
        condition = request.form.get('condition', 'good')
        location = (request.form.get('location') or '').strip()
        is_shared = 'is_shared' in request.form

        errors = []
        if not name:
            errors.append('Asset name is required')
        elif len(name) > 255:
            errors.append('Asset name must be ≤255 characters')
        if not category_id or not AssetCategory.query.get(category_id):
            errors.append('A valid category is required')
        if serial_number and len(serial_number) > 100:
            errors.append('Serial number must be ≤100 characters')
        if not location:
            errors.append('Location is required')
        if condition not in ASSET_CONDITIONS:
            errors.append('Invalid condition')

        parsed_date = None
        if acquisition_date:
            try:
                parsed_date = datetime.strptime(acquisition_date, '%Y-%m-%d').date()
                if parsed_date > datetime.now().date():
                    errors.append('Acquisition date cannot be in the future')
            except ValueError:
                errors.append('Invalid acquisition date')

        parsed_cost = None
        if acquisition_cost:
            try:
                parsed_cost = float(acquisition_cost)
                if parsed_cost < 0:
                    errors.append('Acquisition cost cannot be negative')
            except ValueError:
                errors.append('Acquisition cost must be a number')

        if errors:
            for e in errors:
                flash(e, 'error')
            return redirect(url_for('assets.register'))

        asset = Asset(
            tag=generate_asset_tag(),
            name=name,
            category_id=int(category_id),
            serial_number=serial_number or None,
            acquisition_date=parsed_date,
            acquisition_cost=parsed_cost,
            condition=condition,
            location=location,
            is_shared=is_shared,
            status='available',
        )
        db.session.add(asset)
        db.session.flush()
        log_activity(current_user.id, f'Registered asset {asset.tag} ({name})', 'asset', asset.id)
        db.session.commit()
        flash(f'Asset {asset.tag} registered', 'success')
        return redirect(url_for('assets.detail', id=asset.id))

    categories = AssetCategory.query.order_by(AssetCategory.name).all()
    return render_template('assets/register.html', categories=categories)


@assets_bp.route('/', methods=['GET'])
@login_required
def list_assets():
    status = request.args.get('status', '')
    category_id = request.args.get('category_id', '')
    location = request.args.get('location', '')
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)

    query = Asset.query

    if status:
        query = query.filter_by(status=status)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if location:
        query = query.filter(Asset.location.ilike(f'%{location}%'))
    if search:
        like = f'%{search}%'
        query = query.filter(
            (Asset.tag.ilike(like)) | (Asset.name.ilike(like)) | (Asset.serial_number.ilike(like))
        )

    pagination = query.order_by(Asset.id.desc()).paginate(page=page, per_page=20, error_out=False)
    categories = AssetCategory.query.order_by(AssetCategory.name).all()

    return render_template(
        'assets/list.html', pagination=pagination, assets=pagination.items,
        categories=categories, statuses=ASSET_STATUSES,
        filters=dict(status=status, category_id=category_id, location=location, search=search),
    )


@assets_bp.route('/<int:id>', methods=['GET'])
@login_required
def detail(id):
    asset = Asset.query.get_or_404(id)
    users = User.query.filter_by(status='active').order_by(User.name).all()
    return render_template('assets/detail.html', asset=asset, users=users)


@assets_bp.route('/<int:id>/retire', methods=['POST'])
@login_required
@require_role('admin', 'asset_manager')
def retire(id):
    asset = Asset.query.get_or_404(id)
    if asset.status == 'allocated':
        flash('Cannot retire an asset that is currently allocated. Return it first.', 'error')
        return redirect(url_for('assets.detail', id=id))
    asset.status = 'retired'
    log_activity(current_user.id, f'Retired asset {asset.tag}', 'asset', asset.id)
    db.session.commit()
    flash(f'Asset {asset.tag} retired', 'success')
    return redirect(url_for('assets.detail', id=id))
