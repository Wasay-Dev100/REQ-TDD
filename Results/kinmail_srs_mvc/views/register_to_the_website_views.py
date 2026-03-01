def render_register(errors):
    return render_template('register_to_the_website_register.html', errors=errors)

def render_verification_sent(email):
    return render_template('register_to_the_website_verification_sent.html', email=email)

def render_verification_result(status):
    return render_template('register_to_the_website_verification_result.html', status=status)