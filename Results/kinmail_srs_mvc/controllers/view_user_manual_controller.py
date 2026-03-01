from flask import Blueprint, jsonify, render_template
from app import db
from models.view_user_manual_manual_section import ManualSection

view_user_manual_bp = Blueprint('view_user_manual', __name__)

@view_user_manual_bp.route('/help', methods=['GET'])
def help_page():
    ensure_default_manual_sections()
    sections = get_published_sections()
    return render_template('view_user_manual_help.html', sections=sections)

@view_user_manual_bp.route('/api/help/manual', methods=['GET'])
def get_user_manual():
    ensure_default_manual_sections()
    sections = get_published_sections()
    return jsonify(serialize_manual(sections))

def ensure_default_manual_sections():
    default_sections = [
        {
            "slug": "registration",
            "title": "Registration",
            "content_md": "Instructions for creating an account, verifying email (if applicable), and completing profile setup.",
            "display_order": 1,
            "is_published": True
        },
        {
            "slug": "password_recovery",
            "title": "Password Recovery",
            "content_md": "Instructions for requesting a password reset, receiving the reset link/code, and setting a new password.",
            "display_order": 2,
            "is_published": True
        },
        {
            "slug": "product_search",
            "title": "Product Search",
            "content_md": "Instructions for searching products, using filters/sorting (if available), and viewing product details.",
            "display_order": 3,
            "is_published": True
        },
        {
            "slug": "contacting_sellers",
            "title": "Contacting Sellers",
            "content_md": "Instructions for contacting sellers via the platform, what information to include, and safety tips.",
            "display_order": 4,
            "is_published": True
        }
    ]

    for section_data in default_sections:
        section = ManualSection.query.filter_by(slug=section_data['slug']).first()
        if not section:
            section = ManualSection(**section_data)
            db.session.add(section)
    db.session.commit()

def get_published_sections():
    return ManualSection.query.filter_by(is_published=True).order_by(ManualSection.display_order).all()