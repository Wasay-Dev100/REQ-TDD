from flask import Blueprint, request, jsonify
from app import db
from models.contact_developer_message import ContactDeveloperMessage
from views.contact_developer_views import render_contact_developer_page

contact_developer_bp = Blueprint("contact_developer", __name__)


@contact_developer_bp.route("/contact-developer", methods=["GET"])
def contact_developer_page():
    social_links = get_contact_developer_social_links()
    return render_contact_developer_page(social_links)


@contact_developer_bp.route("/contact-developer", methods=["POST"])
def submit_contact_developer():
    payload = request.get_json(silent=True)
    errors = validate_contact_developer_payload(payload)
    if errors:
        return jsonify({"errors": errors}), 400

    msg = create_contact_developer_message(
        name=payload["name"],
        email=payload["email"],
        message=payload["message"],
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify(msg.to_dict()), 201


@contact_developer_bp.route("/contact-developer/social-links", methods=["GET"])
def get_social_links():
    return jsonify(get_contact_developer_social_links())


def get_contact_developer_social_links():
    return {
        "twitter": "https://twitter.com/developer",
        "linkedin": "https://linkedin.com/in/developer",
        "github": "https://github.com/developer",
    }


def validate_contact_developer_payload(payload):
    errors = {}

    if payload is None:
        errors["payload"] = "Payload is required."
        return errors
    if not isinstance(payload, dict):
        errors["payload"] = "Payload must be a dict."
        return errors

    name = payload.get("name")
    email = payload.get("email")
    message = payload.get("message")

    if name is None or (isinstance(name, str) and not name.strip()):
        errors["name"] = "Name is required."
    elif not isinstance(name, str):
        errors["name"] = "Name must be a string."
    elif len(name.strip()) > 120:
        errors["name"] = "Name must be at most 120 characters."

    if email is None or (isinstance(email, str) and not email.strip()):
        errors["email"] = "Email is required."
    elif not isinstance(email, str):
        errors["email"] = "Email must be a string."
    else:
        email_str = email.strip()
        if len(email_str) > 254:
            errors["email"] = "Email must be at most 254 characters."
        elif "@" not in email_str or email_str.startswith("@") or email_str.endswith("@"):
            errors["email"] = "Email must be a valid email address."

    if message is None or (isinstance(message, str) and not message.strip()):
        errors["message"] = "Message is required."
    elif not isinstance(message, str):
        errors["message"] = "Message must be a string."

    return errors


def create_contact_developer_message(name, email, message):
    if not isinstance(name, str):
        raise TypeError("name must be a string.")
    if not isinstance(email, str):
        raise TypeError("email must be a string.")
    if not isinstance(message, str):
        raise TypeError("message must be a string.")

    name = name.strip()
    email = email.strip()
    message = message.strip()

    if not name:
        raise ValueError("name is required.")
    if not email:
        raise ValueError("email is required.")
    if not message:
        raise ValueError("message is required.")

    if len(name) > 120:
        raise ValueError("name must be at most 120 characters.")
    if len(email) > 254:
        raise ValueError("email must be at most 254 characters.")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("email must be a valid email address.")

    return ContactDeveloperMessage(name=name, email=email, message=message)