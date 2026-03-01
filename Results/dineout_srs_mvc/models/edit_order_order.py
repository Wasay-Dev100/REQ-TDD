from app import db
from datetime import datetime

class EditOrderOrder(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, index=True)
    status = db.Column(db.String(20), index=True)
    version = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_editable(self):
        return self.status not in ['served', 'cancelled']