from app import db
from datetime import datetime

class CancelOrderCancellationRequest(db.Model):
    __tablename__ = 'cancellation_requests'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True, nullable=False)
    requested_by_user_id = db.Column(db.Integer, index=True, nullable=False)
    status = db.Column(db.String(30), index=True, nullable=False)
    customer_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=True, default=datetime.utcnow, onupdate=datetime.utcnow)