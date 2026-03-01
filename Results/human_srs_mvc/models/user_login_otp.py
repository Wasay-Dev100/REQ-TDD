from datetime import datetime

from app import db


class UserLoginOtp(db.Model):
    __tablename__ = "user_login_otps"
    __table_args__ = {"extend_existing": True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    otp_code_hash = db.Column(db.String(255), nullable=False)
    purpose = db.Column(db.String(40), default="login_2fa")
    expires_at = db.Column(db.DateTime, nullable=False)
    consumed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_expired(self):
        if self.expires_at is None:
            return True
        return datetime.utcnow() > self.expires_at

    def is_consumed(self):
        return self.consumed_at is not None