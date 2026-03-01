from app import db
from datetime import datetime


class Payment(db.Model):
    __tablename__ = "payments"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    method = db.Column(db.String(20), nullable=False)
    reference = db.Column(db.String(64), nullable=True)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)