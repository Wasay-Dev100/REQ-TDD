from flask import render_template


def render_staff_list(staff):
    return render_template("add_edit_delete_staff_members_staff_list.html", staff=staff)


def render_staff_form(mode, staff, errors):
    return render_template(
        "add_edit_delete_staff_members_staff_form.html",
        mode=mode,
        staff=staff,
        errors=errors,
    )