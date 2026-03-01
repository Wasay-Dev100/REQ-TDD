from app import db

class DishCategory(db.Model):
    __tablename__ = 'chef_order_queue_dish_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, index=True)
    name = db.Column(db.String(80), unique=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name
        }