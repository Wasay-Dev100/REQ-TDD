from flask import render_template


def render_tables_page(tables: list[dict]) -> str:
    return render_template("hall_manager_operations_tables.html", tables=tables)


def render_notifications_page(notifications: list[dict]) -> str:
    return render_template("hall_manager_operations_notifications.html", notifications=notifications)