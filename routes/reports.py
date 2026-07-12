import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, render_template, Response
from flask_login import login_required

from models import Asset, Allocation, Booking, MaintenanceRequest, Department, AssetCategory
from utils import require_role

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

RETIREMENT_AGE_YEARS = 4


@reports_bp.route('/', methods=['GET'])
@login_required
@require_role('admin', 'asset_manager', 'dept_head')
def index():
    assets = Asset.query.all()

    # Utilization: rank by combined allocation + booking activity count.
    activity_counts = defaultdict(int)
    for a in assets:
        activity_counts[a.id] += len(a.allocations) + len(a.bookings)
    ranked = sorted(assets, key=lambda a: activity_counts[a.id], reverse=True)
    most_used = [(a, activity_counts[a.id]) for a in ranked[:5] if activity_counts[a.id] > 0]
    idle = [(a, activity_counts[a.id]) for a in ranked[::-1][:5] if a.status != 'retired']

    # Maintenance frequency by category.
    maintenance_by_category = defaultdict(int)
    for m in MaintenanceRequest.query.all():
        maintenance_by_category[m.asset.category.name] += 1
    maintenance_by_category = sorted(maintenance_by_category.items(), key=lambda x: x[1], reverse=True)

    # Assets due for maintenance / nearing retirement.
    today = datetime.now().date()
    nearing_retirement = [
        a for a in assets
        if a.acquisition_date and (today - a.acquisition_date).days >= RETIREMENT_AGE_YEARS * 365
        and a.status not in ('retired', 'disposed')
    ]
    due_for_maintenance = []
    for a in assets:
        if a.status in ('retired', 'disposed', 'under_maintenance'):
            continue
        if a.category.warranty_period_days and a.acquisition_date:
            warranty_end = a.acquisition_date + timedelta(days=a.category.warranty_period_days)
            days_left = (warranty_end - today).days
            if 0 <= days_left <= 30:
                due_for_maintenance.append((a, days_left))

    # Department-wise allocation summary.
    dept_summary = defaultdict(int)
    for alloc in Allocation.query.filter_by(status='active').all():
        if alloc.dept_id:
            dept_summary[alloc.department.name] += 1
        elif alloc.user and alloc.user.department:
            dept_summary[alloc.user.department.name] += 1
        else:
            dept_summary['Unassigned'] += 1
    dept_summary = sorted(dept_summary.items(), key=lambda x: x[1], reverse=True)

    # Booking heatmap: count by hour-of-day bucket across all bookings.
    heatmap = defaultdict(int)
    for b in Booking.query.filter(Booking.status != 'cancelled').all():
        heatmap[b.start_time.hour] += 1
    heatmap_data = [(h, heatmap.get(h, 0)) for h in range(24)]
    max_heat = max([v for _, v in heatmap_data] + [1])

    return render_template(
        'reports/index.html',
        most_used=most_used, idle=idle,
        maintenance_by_category=maintenance_by_category,
        nearing_retirement=nearing_retirement, due_for_maintenance=due_for_maintenance,
        dept_summary=dept_summary,
        heatmap_data=heatmap_data, max_heat=max_heat,
    )


@reports_bp.route('/export.csv', methods=['GET'])
@login_required
@require_role('admin', 'asset_manager', 'dept_head')
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Tag', 'Name', 'Category', 'Status', 'Location', 'Condition', 'Current Holder', 'Acquisition Date', 'Acquisition Cost'])
    for a in Asset.query.order_by(Asset.tag).all():
        holder = a.current_allocation.holder_name if a.current_allocation else ''
        writer.writerow([
            a.tag, a.name, a.category.name, a.status, a.location, a.condition, holder,
            a.acquisition_date.strftime('%Y-%m-%d') if a.acquisition_date else '',
            a.acquisition_cost or '',
        ])

    return Response(
        output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=orbyn_asset_report.csv'},
    )
