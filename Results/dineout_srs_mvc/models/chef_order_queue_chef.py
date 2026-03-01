from app import db

class Chef(db.Model):
    __tablename__ = 'chef_order_queue_chefs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True, index=True)
    display_name = db.Column(db.String(80), index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=db.func.utcnow, index=True)

    def is_specialized_for(self, dish_category):
        # Logic to determine if chef is specialized for the dish_category
        pass