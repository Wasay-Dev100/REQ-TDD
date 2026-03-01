from app import db
from datetime import datetime

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), index=True, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), index=True, nullable=False)
    product_name_snapshot = db.Column(db.String(120), nullable=False)
    unit_price_cents_snapshot = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    special_instructions = db.Column(db.String(500), nullable=True)
    line_total_cents = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def recalculate_line_total(self):
        self.line_total_cents = self.unit_price_cents_snapshot * self.quantity