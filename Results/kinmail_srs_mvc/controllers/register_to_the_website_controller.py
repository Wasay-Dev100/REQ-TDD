from flask import Blueprint, request, redirect, url_for, flash
from app import db, mail
from models.user import User
from views.register_to_the_website_views import render_register, render_verify_email_sent
from werkzeug.datastructures import ImmutableMultiDict, FileStorage
from flask_mail import Message
import os
import random
import string

register_to_the_website_bp = Blueprint('register_to_the_website', __name__)

@register_to_the_website_bp.route('/register', methods=['GET'])
def show_register():
    return render_register(errors=None, prefill=None)

@register_to_the_website_bp.route('/register', methods=['POST'])
def register():
    form = request.form
    files = request.files
    errors = validate_registration_payload(form, files)
    if errors:
        return render_register(errors=errors, prefill=form)

    user = User(
        first_name=form['first_name'],
        middle_name=form.get('middle_name', ''),
        last_name=form['last_name'],
        gender=form['gender'],
        contact_number=form['contact_number'],
        birthdate=form['birthdate'],
        username=form['username'],
        email=form['email']
    )
    user.set_password(form['password'])
    profile_picture_path = save_profile_picture(files['profile_picture'], user.username)
    user.profile_picture_path = profile_picture_path

    verification_token = generate_verification_token(32)
    user.set_email_verification_token(verification_token)
    user.email_verification_sent_at = func.now()

    db.session.add(user)
    db.session.commit()

    verification_url = url_for('register_to_the_website.verify_email', token=verification_token, _external=True)
    send_verification_email(user.email, verification_url)

    return render_verify_email_sent(email=user.email)

@register_to_the_website_bp.route('/verify-email', methods=['GET'])
def verify_email():
    token = request.args.get('token')
    user = User.query.filter_by(email_verification_token_hash=token).first()
    if user and user.check_email_verification_token(token):
        user.is_email_verified = True
        user.email_verified_at = func.now()
        db.session.commit()
        flash('Email verified successfully!', 'success')
        return redirect(url_for('login'))
    else:
        flash('Invalid or expired token.', 'danger')
        return redirect(url_for('register_to_the_website.show_register'))

def validate_registration_payload(form: ImmutableMultiDict, files: ImmutableMultiDict) -> dict:
    errors = {}
    required_fields = ['first_name', 'last_name', 'gender', 'contact_number', 'birthdate', 'username', 'email', 'password']
    for field in required_fields:
        if not form.get(field):
            errors[field] = 'This field is required.'

    if 'profile_picture' not in files or not files['profile_picture']:
        errors['profile_picture'] = 'Profile picture is required.'

    return errors

def save_profile_picture(file_storage: FileStorage, username: str) -> str:
    filename = f"{username}_{file_storage.filename}"
    file_path = os.path.join('static/uploads', filename)
    file_storage.save(file_path)
    return file_path

def generate_verification_token(length: int) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def send_verification_email(email: str, verification_url: str):
    msg = Message('Verify Your Email', recipients=[email])
    msg.body = f'Please click the link to verify your email: {verification_url}'
    mail.send(msg)