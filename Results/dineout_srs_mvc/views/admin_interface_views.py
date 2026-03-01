from flask import render_template


def render_admin_home(current_user) -> str:
    return render_template("admin_interface_home.html", current_user=current_user)


def render_staff_list(current_user, staff_members) -> str:
    return render_template(
        "admin_interface_staff_list.html",
        current_user=current_user,
        staff_members=staff_members,
    )


def render_staff_form(current_user, staff_member, errors, mode) -> str:
    return render_template(
        "admin_interface_staff_form.html",
        current_user=current_user,
        staff_member=staff_member,
        errors=errors,
        mode=mode,
    )


def render_menu_list(current_user, menu_items) -> str:
    return render_template(
        "admin_interface_menu_list.html",
        current_user=current_user,
        menu_items=menu_items,
    )


def render_menu_form(current_user, menu_item, errors, mode) -> str:
    return render_template(
        "admin_interface_menu_form.html",
        current_user=current_user,
        menu_item=menu_item,
        errors=errors,
        mode=mode,
    )


def render_inventory_list(current_user, inventory_items) -> str:
    return render_template(
        "admin_interface_inventory_list.html",
        current_user=current_user,
        inventory_items=inventory_items,
    )


def render_inventory_form(current_user, inventory_item, errors, mode) -> str:
    return render_template(
        "admin_interface_inventory_form.html",
        current_user=current_user,
        inventory_item=inventory_item,
        errors=errors,
        mode=mode,
    )