from flask import render_template


def render_landing(is_authenticated, user):
    return render_template(
        "user_login_landing.html",
        is_authenticated=bool(is_authenticated),
        user=user,
    )