def render_profile_page(user):
    return f"""
    <html>
    <head><title>Profile Page</title></head>
    <body>
        <h1>{user.name}'s Profile</h1>
        <p><strong>Username:</strong> {user.username}</p>
        <p><strong>Email:</strong> {user.email}</p>
        <p><strong>Contact Number:</strong> {user.contact_number}</p>
        <p><strong>Birthdate:</strong> {user.birthdate}</p>
        <p><strong>Gender:</strong> {user.gender}</p>
        <img src="{user.profile_picture_url}" alt="Profile Picture" />
    </body>
    </html>
    """