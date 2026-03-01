from app import db
from datetime import datetime

class ProductOffer(db.Model):
    __tablename__ = 'product_offers'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('sellers.id'), index=True)
    currency = db.Column(db.String(3), default='USD')
    list_price = db.Column(db.Numeric(10, 2), nullable=True)
    sale_price = db.Column(db.Numeric(10, 2), nullable=False)
    stock_quantity = db.Column(db.Integer, default=0)
    delivery_fee = db.Column(db.Numeric(10, 2), default=0)
    delivery_estimate_days_min = db.Column(db.Integer, nullable=True)
    delivery_estimate_days_max = db.Column(db.Integer, nullable=True)
    warranty_months = db.Column(db.Integer, nullable=True)
    warranty_terms = db.Column(db.Text, nullable=True)
    return_policy = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_pricing_delivery_warranty_dict(self):
        return {
            "currency": self.currency,
            "list_price": str(self.list_price) if self.list_price else None,
            "sale_price": str(self.sale_price),
            "delivery_fee": str(self.delivery_fee),
            "estimate_days_min": self.delivery_estimate_days_min,
            "estimate_days_max": self.delivery_estimate_days_max,
            "warranty_months": self.warranty_months,
            "warranty_terms": self.warranty_terms
        }