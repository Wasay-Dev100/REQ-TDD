from flask import render_template
from models.user import User

def render_admin_dashboard(current_user: User) -> str:
    return render_template('admin_database_management_dashboard.html', user=current_user)