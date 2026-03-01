from flask import render_template


def render_menu_item_list(menu_items: list):
    return render_template(
        "add_edit_delete_menu_items_menu_items.html", menu_items=menu_items
    )


def render_menu_item_form(mode: str, menu_item=None, errors=None):
    return render_template(
        "add_edit_delete_menu_items_menu_item_form.html",
        mode=mode,
        menu_item=menu_item,
        errors=errors,
    )