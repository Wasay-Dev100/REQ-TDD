from flask import Blueprint, request, redirect, url_for, session, render_template
from app import db
from models.user import User
from views.user_login_views import render_login

user_login_bp = Blueprint('user_login_bp', __name__)

@user_login_bp.route('/login', methods=['GET'])
def login_get():
    next_url = request.args.get('next', '')
    return render_login(next_url=next_url)

@user_login_bp.route('/login', methods=['POST'])
def login_post():
    identifier = request.form.get('identifier', '')
    password = request.form.get('password', '')
    next_url = request.form.get('next', '')

    if not identifier or not password:
        return render_login(error="Please provide both identifier and password.", identifier=identifier, next_url=next_url)

    user = _find_user_by_identifier(identifier)
    if not user or not user.check_password(password):
        return render_login(error="Invalid username/email or password.", identifier=identifier, next_url=next_url)

    if not user.is_active:
        return render_login(error="Account is inactive.", identifier=identifier, next_url=next_url)

    session['user_id'] = user.id
    if _is_safe_next_url(next_url):
        return redirect(next_url)
    return redirect(url_for('index'))

@user_login_bp.route('/logout', methods=['POST'])
def logout_post():
    next_url = request.form.get('next', '')
    session.pop('user_id', None)
    if _is_safe_next_url(next_url):
        return redirect(next_url)
    return redirect(url_for('user_login_bp.login_get'))

def _find_user_by_identifier(identifier: str) -> User | None:
    if '@' in identifier:
        return User.query.filter_by(email=identifier.lower()).first()
    return User.query.filter_by(username=identifier).first()

def _is_safe_next_url(target: str) -> bool:
    from urllib.parse import urlparse, urljoin
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc