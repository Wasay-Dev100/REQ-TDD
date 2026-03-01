def render_new_product_form(categories):
    # Render the HTML form for adding a new product
    return render_template('add_product_new.html', categories=categories)

def json_product_created(product):
    return {
        'id': product.id,
        'name': product.name,
        'category': product.category.to_dict(),
        'picture_url': product.picture_url,
        'owner': {
            'user_id': product.owner_user_id,
            'owner_name': product.owner_name
        },
        'description': product.description,
        'price': {
            'amount': product.price_amount,
            'currency': product.price_currency
        },
        'condition': product.condition,
        'warranty_months': product.warranty_months,
        'delivery': {
            'method': product.delivery_method,
            'cost_amount': product.delivery_cost_amount,
            'notes': product.delivery_notes
        },
        'created_at': product.created_at.isoformat()
    }

def json_error(message, status_code, errors):
    return {
        'error': 'validation_error',
        'message': message,
        'errors': errors
    }