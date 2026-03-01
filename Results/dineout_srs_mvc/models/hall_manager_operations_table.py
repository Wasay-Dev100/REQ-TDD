from datetime import datetime

from app import db


class HallManagerOperationsTable(db.Model):
    __tablename__ = "hall_manager_operations_tables"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    firebase_table_id = db.Column(db.String(128), unique=True, index=True)
    table_number = db.Column(db.Integer, unique=True, index=True)
    capacity = db.Column(db.Integer)
    status = db.Column(db.String(30), index=True)
    reserved_by_name = db.Column(db.String(120), nullable=True)
    reserved_by_phone = db.Column(db.String(40), nullable=True)
    reservation_time = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": int(self.id) if self.id is not None else None,
            "firebase_table_id": self.firebase_table_id,
            "table_number": int(self.table_number) if self.table_number is not None else None,
            "capacity": int(self.capacity) if self.capacity is not None else None,
            "status": self.status,
            "reserved_by_name": self.reserved_by_name,
            "reserved_by_phone": self.reserved_by_phone,
            "reservation_time": self.reservation_time.isoformat() if self.reservation_time else None,
            "notes": self.notes,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }