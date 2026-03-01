from flask import Blueprint, render_template
from views.view_website_user_manual_views import render_help_page

view_website_user_manual_bp = Blueprint('view_website_user_manual', __name__)

@view_website_user_manual_bp.route('/help', methods=['GET'])
def help_page():
    sections = get_user_manual_sections()
    return render_help_page(sections)

def get_user_manual_sections() -> dict[str, dict[str, str]]:
    return {
        "registration": {
            "title": "Registration",
            "content": "Instructions on how to register on the platform."
        },
        "password_recovery": {
            "title": "Password Recovery",
            "content": "Steps to recover your password."
        },
        "product_search": {
            "title": "Product Search",
            "content": "How to search for products on the platform."
        },
        "contact_sellers": {
            "title": "Contacting Sellers",
            "content": "Guidelines on how to contact sellers."
        }
    }