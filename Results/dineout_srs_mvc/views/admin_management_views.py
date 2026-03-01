from flask import render_template


def render_admin_dashboard(
    staff: list[dict], menu_items: list[dict], inventory_items: list[dict]
) -> str:
    return render_template(
        "admin_management_dashboard.html",
        staff=staff,
        menu_items=menu_items,
        inventory_items=inventory_items,
    )