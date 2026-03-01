from datetime import datetime
from app import db


class EventProposal(db.Model):
    __tablename__ = "event_proposals"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, index=True, nullable=False)
    proposed_by_user_id = db.Column(db.Integer, index=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(200), nullable=True)
    start_at = db.Column(db.DateTime, index=True, nullable=False)
    end_at = db.Column(db.DateTime, index=True, nullable=False)
    status = db.Column(db.String(20), default="PENDING", index=True, nullable=False)
    reviewed_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    decision_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def approve(self, reviewer_user, reason):
        self.status = "APPROVED"
        self.reviewed_by_user_id = reviewer_user.id
        self.reviewed_at = datetime.utcnow()
        self.decision_reason = reason

    def decline(self, reviewer_user, reason):
        self.status = "DECLINED"
        self.reviewed_by_user_id = reviewer_user.id
        self.reviewed_at = datetime.utcnow()
        self.decision_reason = reason

    def to_dict(self):
        return {
            "id": self.id,
            "club_id": self.club_id,
            "proposed_by_user_id": self.proposed_by_user_id,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "start_at": self.start_at.isoformat() if self.start_at else None,
            "end_at": self.end_at.isoformat() if self.end_at else None,
            "status": self.status,
            "reviewed_by_user_id": self.reviewed_by_user_id,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "decision_reason": self.decision_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }