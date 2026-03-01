from app import db
from decimal import Decimal


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    sku = db.Column(db.String(64), unique=True)
    category_id = db.Column(db.Integer, index=True)
    seller_id = db.Column(db.Integer, index=True)
    short_description = db.Column(db.String(500))
    description = db.Column(db.Text)
    currency = db.Column(db.String(3))
    list_price = db.Column(db.Numeric(10, 2))
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)
    stock_quantity = db.Column(db.Integer)
    condition = db.Column(db.String(20))
    brand = db.Column(db.String(80), nullable=True)
    model_number = db.Column(db.String(80), nullable=True)
    weight_kg = db.Column(db.Numeric(8, 3), nullable=True)
    dimensions_cm = db.Column(db.String(60), nullable=True)
    delivery_method = db.Column(db.String(30))
    delivery_fee = db.Column(db.Numeric(10, 2))
    delivery_estimated_min_days = db.Column(db.Integer)
    delivery_estimated_max_days = db.Column(db.Integer)
    ships_from = db.Column(db.String(120), nullable=True)
    return_policy = db.Column(db.String(255), nullable=True)
    warranty_type = db.Column(db.String(30))
    warranty_period_months = db.Column(db.Integer, nullable=True)
    warranty_details = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    def get_effective_price(self) -> Decimal:
        return self.sale_price if self.sale_price is not None else self.list_price