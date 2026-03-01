from flask import render_template

def render_login(error: str | None = None, identifier: str | None = None) -> str:
    return render_template('login_login.html', error=error, identifier=identifier)