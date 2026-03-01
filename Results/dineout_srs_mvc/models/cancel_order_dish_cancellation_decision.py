from app import db
from datetime import datetime

class CancelOrderDishCancellationDecision(db.Model):
    __tablename__ = 'dish_cancellation_decisions'

    id = db.Column(db.Integer, primary_key=True)
    cancellation_request_id = db.Column(db.Integer, index=True, nullable=False)
    order_item_id = db.Column(db.Integer, index=True, nullable=False)
    decision_status = db.Column(db.String(30), index=True, nullable=False)
    decided_by_user_id = db.Column(db.Integer, nullable=True, index=True)
    decision_note = db.Column(db.String(255), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=True, default=datetime.utcnow, onupdate=datetime.utcnow)