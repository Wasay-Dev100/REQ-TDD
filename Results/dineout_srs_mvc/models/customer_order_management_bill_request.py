from app import db
from datetime import datetime

class BillRequest(db.Model):
    __tablename__ = 'bill_requests'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), index=True, nullable=False)
    requested_by_customer_id = db.Column(db.Integer, index=True, nullable=False)
    status = db.Column(db.String(20), index=True, nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.String(500), nullable=True)