from app import db
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM

product_condition_enum = ENUM('new', 'like_new', 'good', 'fair', 'poor', name='product_condition', create_type=False)
warranty_type_enum = ENUM('none', 'manufacturer', 'seller', name='warranty_type', create_type=False)

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), index=True, nullable=False)
    picture_url = db.Column(db.String(512), nullable=False)
    owner_name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price_amount = db.Column(db.Numeric(10, 2), nullable=False)
    price_currency = db.Column(db.String(3), default='USD', nullable=False)
    condition = db.Column(product_condition_enum, nullable=False)
    warranty_type = db.Column(warranty_type_enum, default='none', nullable=False)
    warranty_months = db.Column(db.Integer, nullable=True)
    home_delivery_available = db.Column(db.Boolean, default=False, nullable=False)
    delivery_fee_amount = db.Column(db.Numeric(10, 2), nullable=True)
    delivery_fee_currency = db.Column(db.String(3), nullable=True)
    delivery_details = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True, nullable=False)
    created_at = db.Column(db.DateTime, server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": {
                "id": self.category_id,
                "name": Category.query.get(self.category_id).name
            },
            "picture_url": self.picture_url,
            "owner_name": self.owner_name,
            "description": self.description,
            "price": {
                "amount": float(self.price_amount),
                "currency": self.price_currency
            },
            "condition": self.condition,
            "warranty": {
                "type": self.warranty_type,
                "months": self.warranty_months
            },
            "delivery": {
                "home_delivery_available": self.home_delivery_available,
                "fee": {
                    "amount": float(self.delivery_fee_amount) if self.delivery_fee_amount else None,
                    "currency": self.delivery_fee_currency
                },
                "details": self.delivery_details
            },
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat()
        }