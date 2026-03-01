from app import db
from datetime import datetime

class AdminDatabaseManagementMenuItem(db.Model):
    __tablename__ = 'menu_items'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, unique=True, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True, index=True)
    display_name = db.Column(db.String(120), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "category_id": self.category_id,
            "display_name": self.display_name,
            "sort_order": self.sort_order,
            "is_available": self.is_available,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }