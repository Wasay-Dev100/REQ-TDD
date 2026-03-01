from flask import render_template


def render_manager_bill_requests(items) -> str:
    return render_template("request_bill_manager_bill_requests.html", items=items)