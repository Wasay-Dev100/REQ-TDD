from app import db
from datetime import datetime

class EventRegistrationRegistration(db.Model):
    __tablename__ = 'event_registration_registrations'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)