from app import db

class Order(db.Model):
    __tablename__ = 'chef_order_queue_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), index=True)
    status = db.Column(db.String(30), default='confirmed', index=True)
    confirmed_at = db.Column(db.DateTime, default=db.func.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'customer_name': self.customer_name,
            'status': self.status,
            'confirmed_at': self.confirmed_at
        }