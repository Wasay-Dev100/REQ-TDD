from flask import Blueprint, jsonify, render_template
from app import db
from models.user import User
from views.view_profile_views import render_profile

view_profile_bp = Blueprint('view_profile_bp', __name__)

@view_profile_bp.route('/profile', methods=['GET'])
def profile_page():
    user = get_current_user()
    if user:
        return render_profile(user)
    return "Unauthorized", 401

@view_profile_bp.route('/api/profile', methods=['GET'])
def get_profile_api():
    user = get_current_user()
    if user:
        return jsonify(user.to_profile_dict())
    return jsonify({"error": "Unauthorized"}), 401

def get_current_user() -> User:
    # This function should retrieve the current logged-in user from the session
    # For demonstration, we'll assume a user with ID 1 is logged in
    return User.query.filter_by(id=1).first()

def login_required(view_func: callable) -> callable:
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return "Unauthorized", 401
        return view_func(*args, **kwargs)
    return wrapper