from app import db
from datetime import datetime


class StaffMember(db.Model):
    __tablename__ = "staff_members"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(30), unique=True, nullable=True)
    role_title = db.Column(db.String(80))
    department = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "role_title": self.role_title,
            "department": self.department,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def update_from_dict(self, data):
        if not isinstance(data, dict):
            return
        for field in [
            "first_name",
            "last_name",
            "email",
            "phone",
            "role_title",
            "department",
            "is_active",
        ]:
            if field in data:
                setattr(self, field, data[field])
        self.updated_at = datetime.utcnow()