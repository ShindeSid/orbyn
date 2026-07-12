from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User
from forms import SignupForm, LoginForm
from utils import log_activity

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = SignupForm()
    if form.validate_on_submit():
        # Signup always creates an Employee account. Role promotion happens only
        # in Org Setup (Screen 3), by an Admin — never at signup.
        user = User(
            name=form.name.data.strip(),
            email=form.email.data.lower().strip(),
            role='employee',
            status='active',
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        log_activity(user.id, 'Signed up', 'user', user.id)
        db.session.commit()
        flash('Account created. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.check_password(form.password.data):
            if user.status != 'active':
                flash('Your account has been deactivated. Contact an admin.', 'error')
                return redirect(url_for('auth.login'))
            login_user(user)
            log_activity(user.id, 'Logged in', 'user', user.id)
            db.session.commit()
            flash(f'Welcome back, {user.name}.', 'success')
            return redirect(url_for('dashboard.index'))
        flash('Invalid email or password', 'error')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    log_activity(current_user.id, 'Logged out', 'user', current_user.id)
    db.session.commit()
    logout_user()
    flash('Logged out.', 'success')
    return redirect(url_for('auth.login'))
