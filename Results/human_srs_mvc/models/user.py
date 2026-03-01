from app import db
from datetime import datetime
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash


class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    username = db.Column(db.String(80), unique=True)
    password_hash = db.Column(db.String(255))
    role = db.Column(db.String(50), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def set_password(self, password):
        if password is None or not isinstance(password, str) or not password.strip():
            raise ValueError("password must be a non-empty string")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if password is None or not isinstance(password, str):
            raise ValueError("password must be a string")
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def is_club_coordinator(self):
        return self.role == 'club_coordinator'

    def is_clubs_coordinator(self):
        return self.role == 'clubs_coordinator'