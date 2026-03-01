from app import db

class Dish(db.Model):
    __tablename__ = 'chef_order_queue_dishes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), index=True)
    category_id = db.Column(db.Integer, index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'category_id': self.category_id,
            'is_active': self.is_active,
            'created_at': self.created_at
        }