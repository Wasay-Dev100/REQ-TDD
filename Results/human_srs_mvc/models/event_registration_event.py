from app import db
from datetime import datetime

class EventRegistrationEvent(db.Model):
    __tablename__ = 'event_registration_events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=True)
    capacity = db.Column(db.Integer, nullable=True)
    is_approved = db.Column(db.Boolean, default=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_open_for_registration(self):
        return self.is_approved and (self.capacity is None or self.remaining_capacity() > 0)

    def remaining_capacity(self):
        if self.capacity is None:
            return float('inf')
        return self.capacity - EventRegistrationRegistration.query.filter_by(event_id=self.id).count()