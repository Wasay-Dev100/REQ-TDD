from datetime import datetime

from app import db


class StaffMember(db.Model):
    __tablename__ = "staff_members"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(30), nullable=True)
    position = db.Column(db.String(80))
    hourly_rate = db.Column(db.Numeric(10, 2), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)