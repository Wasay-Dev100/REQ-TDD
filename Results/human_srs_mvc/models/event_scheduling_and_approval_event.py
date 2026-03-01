from datetime import datetime
from app import db


class Event(db.Model):
    __tablename__ = "event_scheduling_and_approval_events"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, index=True, nullable=False)
    proposal_id = db.Column(db.Integer, unique=True, index=True, nullable=False)
    created_from_proposal_id = db.Column(db.Integer, unique=True, index=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(200), nullable=True)
    start_at = db.Column(db.DateTime, index=True, nullable=False)
    end_at = db.Column(db.DateTime, index=True, nullable=False)
    is_published = db.Column(db.Boolean, default=True, index=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "club_id": self.club_id,
            "created_from_proposal_id": self.created_from_proposal_id,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "is_published": bool(self.is_published),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }