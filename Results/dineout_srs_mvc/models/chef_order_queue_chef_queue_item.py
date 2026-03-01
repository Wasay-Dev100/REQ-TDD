from app import db

class ChefQueueItem(db.Model):
    __tablename__ = 'chef_order_queue_chef_queue_items'
    
    id = db.Column(db.Integer, primary_key=True)
    chef_id = db.Column(db.Integer, index=True)
    order_item_id = db.Column(db.Integer, index=True)
    status = db.Column(db.String(30), default='queued', index=True)
    position = db.Column(db.Integer, index=True)
    assigned_at = db.Column(db.DateTime, default=db.func.utcnow, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'chef_id': self.chef_id,
            'order_item_id': self.order_item_id,
            'status': self.status,
            'position': self.position,
            'assigned_at': self.assigned_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at
        }