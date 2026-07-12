from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, validators
from models import User


class SignupForm(FlaskForm):
    name = StringField('Full Name', [
        validators.DataRequired(),
        validators.Length(min=2, max=255),
    ])
    email = StringField('Email', [
        validators.DataRequired(),
        validators.Email(message='Enter a valid email address'),
        validators.Length(min=5, max=255),
    ])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.Length(min=8, message='Password must be at least 8 characters'),
    ])
    confirm = PasswordField('Confirm Password', [
        validators.DataRequired(),
        validators.EqualTo('password', message='Passwords must match'),
    ])

    def validate_email(form, field):
        if User.query.filter_by(email=field.data.lower().strip()).first():
            raise validators.ValidationError('Email already in use')


class LoginForm(FlaskForm):
    email = StringField('Email', [validators.DataRequired(), validators.Email()])
    password = PasswordField('Password', [validators.DataRequired()])
