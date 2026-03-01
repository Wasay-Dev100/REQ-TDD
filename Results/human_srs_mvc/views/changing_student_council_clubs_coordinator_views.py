from flask import render_template


def render_manage_page(current_coordinator, all_users, errors):
    return render_template(
        "changing_student_council_clubs_coordinator_manage.html",
        current_coordinator=current_coordinator,
        all_users=all_users,
        errors=errors,
    )