def serialize_category(category):
    return {
        'id': category.id,
        'name': category.name,
        'description': category.description,
        'is_active': category.is_active,
        'sort_order': category.sort_order
    }

def serialize_product(product):
    return {
        'id': product.id,
        'category_id': product.category_id,
        'name': product.name,
        'description': product.description,
        'price_cents': product.price_cents,
        'image_url': product.image_url,
        'is_available': product.is_available,
        'prep_time_minutes': product.prep_time_minutes
    }

def serialize_order_item(item):
    return {
        'id': item.id,
        'order_id': item.order_id,
        'product_id': item.product_id,
        'product_name_snapshot': item.product_name_snapshot,
        'unit_price_cents_snapshot': item.unit_price_cents_snapshot,
        'quantity': item.quantity,
        'special_instructions': item.special_instructions,
        'line_total_cents': item.line_total_cents,
        'created_at': item.created_at,
        'updated_at': item.updated_at
    }

def serialize_order(order):
    return {
        'id': order.id,
        'customer_id': order.customer_id,
        'table_identifier': order.table_identifier,
        'status': order.status,
        'subtotal_cents': order.subtotal_cents,
        'tax_cents': order.tax_cents,
        'service_charge_cents': order.service_charge_cents,
        'total_cents': order.total_cents,
        'notes': order.notes,
        'created_at': order.created_at,
        'updated_at': order.updated_at,
        'prepared_at': order.prepared_at,
        'cancelled_at': order.cancelled_at
    }

def serialize_bill(order):
    return {
        'order_id': order.id,
        'subtotal_cents': order.subtotal_cents,
        'tax_cents': order.tax_cents,
        'service_charge_cents': order.service_charge_cents,
        'total_cents': order.total_cents
    }

def serialize_feedback(feedback):
    return {
        'id': feedback.id,
        'order_id': feedback.order_id,
        'customer_id': feedback.customer_id,
        'rating': feedback.rating,
        'comment': feedback.comment,
        'created_at': feedback.created_at
    }