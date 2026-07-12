"""
HTTP-triggered equivalent of scheduler.py's background tick, for
environments (like Vercel serverless) that can't keep an in-process
APScheduler thread alive between requests. A Vercel Cron Job hits this
route on a schedule instead of a persistent loop ticking every 60s.

Protected by a shared-secret header so it can't be triggered by anyone
who finds the URL - Vercel's own cron requests include this automatically
when CRON_SECRET is set as a project env var.
"""
import os

from flask import Blueprint, request, jsonify

from scheduler import tick

cron_bp = Blueprint('cron', __name__, url_prefix='/api/cron')


@cron_bp.route('/tick', methods=['GET', 'POST'])
def run_tick():
    expected = os.environ.get('CRON_SECRET')
    if expected:
        auth_header = request.headers.get('Authorization', '')
        if auth_header != f'Bearer {expected}':
            return jsonify({'error': 'unauthorized'}), 401

    from flask import current_app
    tick(current_app._get_current_object())
    return jsonify({'ok': True})
