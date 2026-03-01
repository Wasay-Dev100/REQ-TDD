from app import db
from datetime import datetime


class BillRequest(db.Model):
    __tablename__ = "bill_requests"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default="pending")

    def mark_processed(self):
        self.status = "processed"