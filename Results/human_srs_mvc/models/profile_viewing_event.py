from datetime import datetime

from app import db
from sqlalchemy import Enum


class ProfileViewingEvent(db.Model):
    __tablename__ = "events"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(200), nullable=True)
    start_at = db.Column(db.DateTime)
    end_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(Enum("DRAFT", "PUBLISHED", "CANCELLED", name="event_status"))
    capacity = db.Column(db.Integer, nullable=True)
    created_by_user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_public_dict(self):
        status_value = self.status.value if hasattr(self.status, "value") else self.status
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "status": status_value,
            "capacity": self.capacity,
        }