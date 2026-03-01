from datetime import datetime

from app import db


class EventProposal(db.Model):
    __tablename__ = "event_proposals"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    proposed_date = db.Column(db.Date)
    location = db.Column(db.String(200))
    club_name = db.Column(db.String(120), index=True)
    submitted_by_user_id = db.Column(db.Integer, index=True)
    status = db.Column(db.String(20), default="PENDING", index=True)
    reviewed_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    review_decision = db.Column(db.String(20), nullable=True)
    review_comment = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def approve(self, reviewer_user, comment=None):
        if reviewer_user is None or not hasattr(reviewer_user, "id") or reviewer_user.id is None:
            raise ValueError("Invalid reviewer_user")
        if not self.is_pending():
            raise ValueError("Only pending proposals can be approved")
        self.status = "APPROVED"
        self.review_decision = "APPROVED"
        self.review_comment = comment
        self.reviewed_by_user_id = int(reviewer_user.id)
        self.reviewed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def reject(self, reviewer_user, comment=None):
        if reviewer_user is None or not hasattr(reviewer_user, "id") or reviewer_user.id is None:
            raise ValueError("Invalid reviewer_user")
        if not self.is_pending():
            raise ValueError("Only pending proposals can be rejected")
        self.status = "REJECTED"
        self.review_decision = "REJECTED"
        self.review_comment = comment
        self.reviewed_by_user_id = int(reviewer_user.id)
        self.reviewed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def is_pending(self):
        return (self.status or "").strip().upper() == "PENDING"