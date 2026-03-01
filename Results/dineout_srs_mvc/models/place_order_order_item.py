from app import db

class PlaceOrderOrderItem(db.Model):
    __tablename__ = 'place_order_order_items'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('place_order_orders.id'), index=True, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), index=True, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price_cents = db.Column(db.Integer, nullable=False)
    line_total_cents = db.Column(db.Integer, nullable=False)

    def compute_line_total(self):
        self.line_total_cents = self.quantity * self.unit_price_cents
        return self.line_total_cents

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "name": self.product.name,
            "quantity": self.quantity,
            "unit_price_cents": self.unit_price_cents,
            "line_total_cents": self.line_total_cents
        }