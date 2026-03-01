from flask import Blueprint, request, redirect, url_for, flash
from app import db
from models.user import User
from views.login_views import render_login

login_bp = Blueprint('login_bp', __name__)

@login_bp.route('/login', methods=['GET'])
def login_get():
    return render_login()

@login_bp.route('/login', methods=['POST'])
def login_post():
    identifier = request.form.get('identifier')
    password = request.form.get('password')
    user = authenticate_user(identifier, password)
    if user:
        login_user_session(user)
        return redirect(url_for('home'))
    else:
        flash('Invalid username or password.')
        return render_login(error='Invalid username or password.', identifier=identifier)

@login_bp.route('/logout', methods=['POST'])
def logout_post():
    logout_user_session()
    return redirect(url_for('login_bp.login_get'))

def authenticate_user(identifier: str, password: str) -> User | None:
    user = User.query.filter((User.username == identifier) | (User.email == identifier)).first()
    if user and user.check_password(password):
        return user
    return None

def login_user_session(user: User):
    # Logic to log in the user session
    pass

def logout_user_session():
    # Logic to log out the user session
    pass