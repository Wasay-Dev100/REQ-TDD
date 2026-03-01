from app import db
from datetime import datetime

class ChefQueueItem(db.Model):
    __tablename__ = 'chef_order_queue_queue_items'

    id = db.Column(db.Integer, primary_key=True)
    chef_id = db.Column(db.Integer, db.ForeignKey('chef_order_queue_chefs.id'), index=True)
    kitchen_order_item_id = db.Column(db.Integer, db.ForeignKey('chef_order_queue_order_items.id'), unique=True, index=True)
    queue_status = db.Column(db.String(20), default='queued')
    priority = db.Column(db.Integer, default=0, index=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def mark_started(self):
        self.queue_status = 'in_progress'
        self.started_at = datetime.utcnow()

    def mark_completed(self):
        self.queue_status = 'completed'
        self.completed_at = datetime.utcnow()