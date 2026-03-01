from app import db
from datetime import datetime

class Order(db.Model):
    __tablename__ = 'head_chef_order_assignment_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(30), default='in_progress', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, index=True, onupdate=datetime.utcnow)
    firebase_order_id = db.Column(db.String(128), unique=True, nullable=True, index=True)

    def recompute_status_from_dishes(self):
        # Logic to recompute order status based on dish statuses
        pass