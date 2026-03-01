from flask import Blueprint, request, redirect, url_for, render_template, jsonify
from app import db, mail
from models.user import User
from views.user_registration_views import render_register_page, render_register_success_page, render_verification_failed_page
from flask_mail import Message
from datetime import datetime
import os
import uuid

user_registration_bp = Blueprint('user_registration', __name__)

@user_registration_bp.route('/register', methods=['GET'])
def register_get():
    return render_register_page()

@user_registration_bp.route('/register', methods=['POST'])
def register_post():
    payload = request.form.to_dict()
    profile_picture = request.files.get('profile_picture')

    validation_errors = validate_registration_payload(payload)
    if validation_errors:
        return jsonify({"error": "validation_error", "details": validation_errors}), 400

    if User.query.filter_by(username=payload['username']).first():
        return jsonify({"error": "conflict", "field": "username"}), 409

    if User.query.filter_by(email=payload['email']).first():
        return jsonify({"error": "conflict", "field": "email"}), 409

    user = User(
        first_name=payload['first_name'],
        middle_name=payload.get('middle_name'),
        last_name=payload['last_name'],
        gender=payload['gender'],
        contact_number=payload['contact_number'],
        birthdate=datetime.strptime(payload['birthdate'], '%Y-%m-%d').date(),
        username=payload['username'],
        email=payload['email']
    )
    user.set_password(payload['password'])

    if profile_picture:
        user.profile_picture_path = save_profile_picture(profile_picture, 'static/uploads/user_registration/profile_pictures')

    raw_token = generate_email_verification_token(user.id, user.email)
    user.set_email_verification_token(raw_token)
    user.email_verification_sent_at = datetime.utcnow()

    db.session.add(user)
    db.session.commit()

    verification_url = url_for('user_registration.verify_email_get', token=raw_token, _external=True)
    send_verification_email(user.email, verification_url)

    return render_register_success_page(user.email), 201

@user_registration_bp.route('/verify-email', methods=['GET'])
def verify_email_get():
    token = request.args.get('token')
    if not token or len(token) < 10:
        return render_verification_failed_page("Invalid or missing token"), 400

    user = User.query.filter_by(email_verification_token_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not user:
        return render_verification_failed_page("Token not found or user not found"), 404

    user.is_email_verified = True
    user.email_verification_token_hash = None
    user.email_verification_sent_at = None
    db.session.commit()

    return redirect(url_for('login'))

def validate_registration_payload(payload: dict) -> dict:
    errors = {}
    # Add validation logic here
    return errors

def save_profile_picture(file_storage, upload_dir: str) -> str:
    filename = f"{uuid.uuid4()}{os.path.splitext(file_storage.filename)[1]}"
    file_path = os.path.join(upload_dir, filename)
    file_storage.save(file_path)
    return file_path

def generate_email_verification_token(user_id: int, email: str) -> str:
    # Generate a token here
    return str(uuid.uuid4())

def send_verification_email(to_email: str, verification_url: str):
    msg = Message('Email Verification', recipients=[to_email])
    msg.body = f'Please verify your email by clicking on the following link: {verification_url}'
    mail.send(msg)