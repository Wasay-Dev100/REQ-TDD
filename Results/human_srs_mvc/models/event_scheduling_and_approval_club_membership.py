from app import db
from datetime import datetime


class ClubMembership(db.Model):
    __tablename__ = 'club_memberships'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, index=True)
    user_id = db.Column(db.Integer, index=True)
    role = db.Column(db.String(50), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def is_coordinator(self):
        return self.role == 'coordinator'