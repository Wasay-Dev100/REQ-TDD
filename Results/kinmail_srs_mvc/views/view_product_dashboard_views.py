from flask import render_template

def render_dashboard(user_id: int | None) -> str:
    return render_template('view_product_dashboard_dashboard.html', user_id=user_id)