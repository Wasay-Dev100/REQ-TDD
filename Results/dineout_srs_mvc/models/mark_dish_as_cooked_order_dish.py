from app import db
from datetime import datetime

class OrderDish(db.Model):
    __tablename__ = 'order_dishes'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), index=True)
    dish_name = db.Column(db.String(120))
    status = db.Column(db.String(30))
    cooked_at = db.Column(db.DateTime, nullable=True)

    def mark_cooked(self):
        self.status = 'cooked'
        self.cooked_at = datetime.utcnow()