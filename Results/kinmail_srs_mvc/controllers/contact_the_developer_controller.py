from flask import Blueprint, request, jsonify, render_template
from app import db, mail
from models.contact_the_developer_message import ContactTheDeveloperMessage
from views.contact_the_developer_views import render_contact_page
from flask_mail import Message

contact_the_developer_bp = Blueprint('contact_the_developer', __name__)

@contact_the_developer_bp.route('/contact', methods=['GET'])
def contact_page():
    social_links = get_configured_social_links()
    return render_contact_page(social_links)

@contact_the_developer_bp.route('/contact', methods=['POST'])
def submit_contact():
    payload = request.json
    valid, errors = validate_contact_payload(payload)
    if not valid:
        return jsonify({'success': False, 'errors': errors}), 400

    contact_message = persist_message(payload['name'], payload['email'], payload['message'])
    if send_contact_message(contact_message):
        return jsonify({'success': True, 'message': 'Contact message sent successfully'}), 200
    else:
        return jsonify({'success': False, 'message': 'Failed to send contact message'}), 500

@contact_the_developer_bp.route('/social-links', methods=['GET'])
def get_social_links():
    social_links = get_configured_social_links()
    return jsonify(social_links)

def validate_contact_payload(payload):
    errors = {}
    if 'name' not in payload or not payload['name']:
        errors['name'] = 'Name is required.'
    if 'email' not in payload or not payload['email']:
        errors['email'] = 'Email is required.'
    if 'message' not in payload or not payload['message']:
        errors['message'] = 'Message is required.'
    return (len(errors) == 0, errors)

def persist_message(name, email, message):
    contact_message = ContactTheDeveloperMessage(name=name, email=email, message=message)
    db.session.add(contact_message)
    db.session.commit()
    return contact_message

def send_contact_message(contact_message):
    try:
        msg = Message(subject="New Contact Message",
                      sender=contact_message.email,
                      recipients=["developer@example.com"],
                      body=f"Name: {contact_message.name}\nEmail: {contact_message.email}\nMessage: {contact_message.message}")
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def get_configured_social_links():
    return [
        {'name': 'Twitter', 'url': 'https://twitter.com/developer'},
        {'name': 'LinkedIn', 'url': 'https://linkedin.com/in/developer'},
        {'name': 'GitHub', 'url': 'https://github.com/developer'}
    ]