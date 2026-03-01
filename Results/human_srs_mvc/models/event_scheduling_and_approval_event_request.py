from app import db
from datetime import datetime


class EventRequest(db.Model):
    __tablename__ = 'event_requests'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, index=True)
    proposed_by_user_id = db.Column(db.Integer, index=True)
    title = db.Column(db.String(200), index=True)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(200), nullable=True)
    start_at = db.Column(db.DateTime, index=True)
    end_at = db.Column(db.DateTime, index=True)
    status = db.Column(db.String(30), default='PENDING', index=True)
    reviewed_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    reviewed_at = db.Column(db.DateTime, nullable=True, index=True)
    decision_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def approve(self, reviewer_user, reason):
        if reviewer_user is None or getattr(reviewer_user, "id", None) is None:
            raise ValueError("reviewer_user is required")
        self.status = 'APPROVED'
        self.reviewed_by_user_id = reviewer_user.id
        self.reviewed_at = datetime.utcnow()
        self.decision_reason = reason
        self.updated_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()

    def decline(self, reviewer_user, reason):
        if reviewer_user is None or getattr(reviewer_user, "id", None) is None:
            raise ValueError("reviewer_user is required")
        self.status = 'DECLINED'
        self.reviewed_by_user_id = reviewer_user.id
        self.reviewed_at = datetime.utcnow()
        self.decision_reason = reason
        self.updated_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()

    def is_pending(self):
        return self.status == 'PENDING'