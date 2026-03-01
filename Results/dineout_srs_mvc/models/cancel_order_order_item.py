from app import db
from datetime import datetime

class CancelOrderOrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True, nullable=False)
    dish_name = db.Column(db.String(120), index=True, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), index=True, nullable=False)
    created_at = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, index=True, default=datetime.utcnow, onupdate=datetime.utcnow)