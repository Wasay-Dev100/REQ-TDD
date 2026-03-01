from datetime import datetime
from app import db


class CustomerFeedbackSubmission(db.Model):
    __tablename__ = "customer_feedback_submissions"

    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.String(64), index=True)
    customer_session_id = db.Column(db.String(64), index=True)
    overall_rating = db.Column(db.Integer, nullable=True)
    comment = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bill_id": self.bill_id,
            "customer_session_id": self.customer_session_id,
            "overall_rating": self.overall_rating,
            "comment": self.comment,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
        }