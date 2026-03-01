def serialize_event(event, current_user_id):
    return {
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'location': event.location,
        'start_at': event.start_at.isoformat(),
        'end_at': event.end_at.isoformat() if event.end_at else None,
        'capacity': event.capacity,
        'is_approved': event.is_approved,
        'approved_at': event.approved_at.isoformat() if event.approved_at else None,
        'created_by_user_id': event.created_by_user_id,
        'created_at': event.created_at.isoformat(),
        'updated_at': event.updated_at.isoformat(),
        'is_registered': is_already_registered(event.id, current_user_id),
        'remaining_capacity': event.remaining_capacity()
    }

def serialize_comment(comment):
    return {
        'id': comment.id,
        'event_id': comment.event_id,
        'user_id': comment.user_id,
        'content': comment.content,
        'created_at': comment.created_at.isoformat(),
        'updated_at': comment.updated_at.isoformat() if comment.updated_at else None
    }