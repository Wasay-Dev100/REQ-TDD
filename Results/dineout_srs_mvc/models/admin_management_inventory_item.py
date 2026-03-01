from datetime import datetime
from app import db


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(120))
    unit = db.Column(db.String(32))
    stock_quantity = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def adjust_stock(self, delta: int) -> int:
        if not isinstance(delta, int):
            raise TypeError("delta must be an int")
        self.stock_quantity = int(self.stock_quantity or 0) + int(delta)
        return int(self.stock_quantity or 0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sku": self.sku,
            "name": self.name,
            "unit": self.unit,
            "stock_quantity": int(self.stock_quantity or 0),
            "reorder_level": int(self.reorder_level or 0),
            "is_active": bool(self.is_active),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }