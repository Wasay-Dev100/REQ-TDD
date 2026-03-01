from app import db
from datetime import datetime


class HallManagerNotification(db.Model):
    __tablename__ = "hall_manager_notifications"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    bill_request_id = db.Column(db.Integer, db.ForeignKey("bill_requests.id"), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
        db.session.add(self)