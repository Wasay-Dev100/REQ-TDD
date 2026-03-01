def render_register_page(errors: dict = None, form_values: dict = None) -> str:
    return render_template('user_registration_register.html', errors=errors, form_values=form_values)

def render_verification_sent_page(email: str) -> str:
    return render_template('user_registration_verification_sent.html', email=email)

def render_verification_result_page(success: bool, message: str) -> str:
    return render_template('user_registration_verification_result.html', success=success, message=message)