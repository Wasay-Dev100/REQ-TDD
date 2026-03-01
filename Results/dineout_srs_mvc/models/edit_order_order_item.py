from app import db
from datetime import datetime

class EditOrderOrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True)
    dish_id = db.Column(db.Integer, index=True)
    dish_name = db.Column(db.String(120))
    unit_price_cents = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def line_total_cents(self):
        return self.unit_price_cents * self.quantity