from datetime import datetime
from app import db


class InventoryTransaction(db.Model):
    __tablename__ = "inventory_transactions"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    inventory_item_id = db.Column(db.Integer, index=True)
    admin_user_id = db.Column(db.Integer, index=True)
    delta = db.Column(db.Integer)
    reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "inventory_item_id": self.inventory_item_id,
            "admin_user_id": self.admin_user_id,
            "delta": self.delta,
            "reason": self.reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }