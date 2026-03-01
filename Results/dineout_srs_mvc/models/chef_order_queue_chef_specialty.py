from app import db

class ChefSpecialty(db.Model):
    __tablename__ = 'chef_order_queue_chef_specialties'
    
    id = db.Column(db.Integer, primary_key=True)
    chef_id = db.Column(db.Integer, index=True)
    dish_category_id = db.Column(db.Integer, index=True)
    priority = db.Column(db.Integer, default=100, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'chef_id': self.chef_id,
            'dish_category_id': self.dish_category_id,
            'priority': self.priority
        }