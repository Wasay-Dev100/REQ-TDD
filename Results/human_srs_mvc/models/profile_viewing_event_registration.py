from datetime import datetime

from app import db
from sqlalchemy import Enum


class ProfileViewingEventRegistration(db.Model):
    __tablename__ = "event_registrations"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    event_id = db.Column(db.Integer)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(Enum("REGISTERED", "CANCELLED", name="registration_status"))

    def to_public_dict(self):
        status_value = self.status.value if hasattr(self.status, "value") else self.status
        return {
            "registration_id": self.id,
            "registration_status": status_value,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
        }