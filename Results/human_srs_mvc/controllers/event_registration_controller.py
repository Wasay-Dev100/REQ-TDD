from flask import Blueprint, render_template, redirect, url_for, request, flash
from app import db
from models.event_registration_event import EventRegistrationEvent
from models.event_registration_registration import EventRegistrationRegistration
from models.event_registration_comment import EventRegistrationComment
from models.user import User
from views.event_registration_views import serialize_event, serialize_comment
from datetime import datetime

event_registration_bp = Blueprint('event_registration_bp', __name__)

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

def login_required(view_func):
    def wrapper(*args, **kwargs):
        if not get_current_user():
            flash("Please log in to continue.")
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)
    return wrapper

def get_approved_event_or_404(event_id):
    event = EventRegistrationEvent.query.filter_by(id=event_id, is_approved=True).first()
    if not event:
        abort(404)
    return event

def is_already_registered(event_id, user_id):
    return EventRegistrationRegistration.query.filter_by(event_id=event_id, user_id=user_id).first() is not None

def count_registrations(event_id):
    return EventRegistrationRegistration.query.filter_by(event_id=event_id).count()

@event_registration_bp.route('/events', methods=['GET'])
def list_events():
    events = EventRegistrationEvent.query.filter_by(is_approved=True).all()
    return render_template('event_registration_events.html', events=[serialize_event(event, get_current_user().id) for event in events])

@event_registration_bp.route('/events/<int:event_id>', methods=['GET'])
def event_detail(event_id):
    event = get_approved_event_or_404(event_id)
    comments = EventRegistrationComment.query.filter_by(event_id=event_id).all()
    is_registered = is_already_registered(event_id, get_current_user().id)
    remaining_capacity = event.remaining_capacity()
    return render_template('event_registration_event_detail.html', event=serialize_event(event, get_current_user().id), comments=[serialize_comment(comment) for comment in comments], is_registered=is_registered, remaining_capacity=remaining_capacity)

@event_registration_bp.route('/events/<int:event_id>/register', methods=['POST'])
@login_required
def register_for_event(event_id):
    event = get_approved_event_or_404(event_id)
    user = get_current_user()
    if is_already_registered(event_id, user.id):
        flash("You are already registered for this event.")
        return redirect(url_for('event_detail', event_id=event_id))
    if event.remaining_capacity() <= 0:
        flash("This event is full.")
        return redirect(url_for('event_detail', event_id=event_id))
    registration = EventRegistrationRegistration(event_id=event_id, user_id=user.id)
    db.session.add(registration)
    db.session.commit()
    flash("Successfully registered for the event.")
    return redirect(url_for('event_registration_bp.list_events'))

@event_registration_bp.route('/events/<int:event_id>/comments', methods=['POST'])
@login_required
def post_comment(event_id):
    event = get_approved_event_or_404(event_id)
    user = get_current_user()
    content = request.form.get('content')
    if not content:
        flash("Comment cannot be empty.")
        return redirect(url_for('event_detail', event_id=event_id))
    comment = EventRegistrationComment(event_id=event_id, user_id=user.id, content=content)
    db.session.add(comment)
    db.session.commit()
    flash("Comment posted successfully.")
    return redirect(url_for('event_detail', event_id=event_id))