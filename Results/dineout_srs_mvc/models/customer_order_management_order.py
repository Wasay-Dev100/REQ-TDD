from app import db
from datetime import datetime

class Order(db.Model):
    __tablename__ = 'orders'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, index=True, nullable=False)
    table_identifier = db.Column(db.String(40), index=True, nullable=False)
    status = db.Column(db.String(20), index=True, nullable=False)
    subtotal_cents = db.Column(db.Integer, nullable=False)
    tax_cents = db.Column(db.Integer, nullable=False)
    service_charge_cents = db.Column(db.Integer, nullable=False)
    total_cents = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, index=True, onupdate=datetime.utcnow)
    prepared_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)

    def is_editable(self) -> bool:
        return self.prepared_at is None and self.cancelled_at is None

    def recalculate_totals(self, tax_rate: float, service_charge_rate: float):
        self.tax_cents = int(self.subtotal_cents * tax_rate)
        self.service_charge_cents = int(self.subtotal_cents * service_charge_rate)
        self.total_cents = self.subtotal_cents + self.tax_cents + self.service_charge_cents