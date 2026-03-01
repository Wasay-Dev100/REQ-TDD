from datetime import datetime
from app import db

class Employee(db.Model):
    __tablename__ = 'employees'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, index=True)
    employee_number = db.Column(db.String(32), unique=True, nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(32), nullable=True)
    role = db.Column(db.String(40), nullable=False)
    hourly_rate_cents = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    hired_at = db.Column(db.DateTime, nullable=True)
    terminated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)