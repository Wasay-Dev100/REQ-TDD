from datetime import datetime
from app import db

class ManualSection(db.Model):
    __tablename__ = 'manual_sections'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True)
    title = db.Column(db.String(120))
    content_md = db.Column(db.Text)
    display_order = db.Column(db.Integer)
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'slug': self.slug,
            'title': self.title,
            'content_md': self.content_md,
            'display_order': self.display_order,
            'is_published': self.is_published,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }