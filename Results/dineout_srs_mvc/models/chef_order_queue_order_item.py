from app import db

class OrderItem(db.Model):
    __tablename__ = 'chef_order_queue_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, index=True)
    dish_id = db.Column(db.Integer, index=True)
    quantity = db.Column(db.Integer, default=1)
    notes = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'dish_id': self.dish_id,
            'quantity': self.quantity,
            'notes': self.notes
        }