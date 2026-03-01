from datetime import datetime

from app import db


class ProfileBadge(db.Model):
    __tablename__ = "profile_badges"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True)
    badge_key = db.Column(db.String(64), index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    granted_by_user_id = db.Column(db.Integer, index=True)
    granted_at = db.Column(db.DateTime, default=datetime.utcnow)
    revoked_by_user_id = db.Column(db.Integer, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)

    def revoke(self, revoked_by_user_id: int):
        if revoked_by_user_id is None:
            raise ValueError("revoked_by_user_id is required")
        try:
            revoked_by_user_id_int = int(revoked_by_user_id)
        except (TypeError, ValueError):
            raise TypeError("revoked_by_user_id must be int")
        self.is_active = False
        self.revoked_by_user_id = revoked_by_user_id_int
        self.revoked_at = datetime.utcnow()