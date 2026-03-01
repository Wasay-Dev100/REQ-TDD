from flask import render_template

def render_login(error: str | None = None, identifier: str = "", next_url: str = "") -> str:
    return render_template('user_login_login.html', error=error, identifier=identifier, next_url=next_url)