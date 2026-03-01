from datetime import datetime

from app import db


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    unit = db.Column(db.String(30))
    quantity = db.Column(db.Numeric(12, 3), default=0)
    reorder_level = db.Column(db.Numeric(12, 3), default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)