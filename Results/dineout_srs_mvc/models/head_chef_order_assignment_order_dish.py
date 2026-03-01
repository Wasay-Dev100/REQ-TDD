from app import db
from datetime import datetime

class OrderDish(db.Model):
    __tablename__ = 'head_chef_order_assignment_order_dishes'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True, nullable=False)
    dish_name = db.Column(db.String(120), index=True, nullable=False)
    specialty_tag = db.Column(db.String(80), nullable=True, index=True)
    quantity = db.Column(db.Integer, default=1, nullable=False)
    status = db.Column(db.String(30), default='pending', index=True)
    assigned_chef_user_id = db.Column(db.Integer, nullable=True, index=True)
    cooked_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, index=True, onupdate=datetime.utcnow)

    def mark_cooked(self):
        self.status = 'cooked'
        self.cooked_at = datetime.utcnow()