from flask import Blueprint, request, session, redirect, url_for, jsonify
from app import db
from models.user import User
from models.category import Category
from models.product import Product
from models.add_product_product_image import ProductImage
from views.add_product_views import render_new_product_form, json_error, json_success
from datetime import datetime
import os
import uuid

add_product_bp = Blueprint('add_product', __name__)

def login_required(view_func):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            if request.accept_mimetypes.accept_json:
                return jsonify({
                    "ok": False,
                    "message": "Authentication required",
                    "errors": {"auth": ["login_required"]}
                }), 401
            else:
                return redirect(url_for('login'))
        return view_func(*args, **kwargs)
    return wrapper

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

def validate_product_payload(form, files):
    errors = {}
    # Validate form fields
    if not form.get('name') or len(form.get('name').strip()) < 3:
        errors['name'] = ['Product name must be at least 3 characters long.']
    if not form.get('category_id') or not form.get('category_id').isdigit() or int(form.get('category_id')) < 1:
        errors['category_id'] = ['Invalid category.']
    if not form.get('owner_name') or len(form.get('owner_name').strip()) < 2:
        errors['owner_name'] = ['Owner name must be at least 2 characters long.']
    if not form.get('description') or len(form.get('description').strip()) < 10:
        errors['description'] = ['Description must be at least 10 characters long.']
    if not form.get('price') or float(form.get('price')) < 0.01:
        errors['price'] = ['Price must be at least 0.01.']
    if form.get('currency') and form.get('currency') not in ['USD', 'EUR', 'GBP']:
        errors['currency'] = ['Invalid currency.']
    if not form.get('condition') or form.get('condition') not in ['new', 'like_new', 'good', 'fair', 'poor']:
        errors['condition'] = ['Invalid condition.']
    if form.get('warranty_months') and (int(form.get('warranty_months')) < 0 or int(form.get('warranty_months')) > 120):
        errors['warranty_months'] = ['Warranty months must be between 0 and 120.']
    if not form.get('delivery_details') or len(form.get('delivery_details').strip()) < 5:
        errors['delivery_details'] = ['Delivery details must be at least 5 characters long.']

    # Validate file fields
    if 'images' in files:
        images = files.getlist('images')
        if len(images) > 5:
            errors['images'] = ['You can upload a maximum of 5 images.']
        for image in images:
            if image.mimetype not in ['image/jpeg', 'image/png', 'image/webp']:
                errors.setdefault('images', []).append('Invalid image type.')
            if len(image.read()) > 5242880:
                errors.setdefault('images', []).append('Image size must not exceed 5MB.')
            image.seek(0)  # Reset file pointer after read

    return errors

def save_uploaded_images(files, upload_dir, allowed_mimetypes, max_images, max_file_size_bytes):
    saved_images = []
    if 'images' in files:
        images = files.getlist('images')
        for image in images[:max_images]:
            if image.mimetype in allowed_mimetypes and len(image.read()) <= max_file_size_bytes:
                image.seek(0)
                filename = f"{uuid.uuid4()}.{image.filename.rsplit('.', 1)[1].lower()}"
                file_path = os.path.join(upload_dir, filename)
                image.save(file_path)
                saved_images.append({
                    'file_path': file_path,
                    'mime_type': image.mimetype,
                    'file_size_bytes': len(image.read())
                })
                image.seek(0)
    return saved_images

@add_product_bp.route('/products/new', methods=['GET'])
@login_required
def new_product():
    categories = Category.query.filter_by(is_active=True).all()
    return render_new_product_form(categories, {}, {})

@add_product_bp.route('/products', methods=['POST'])
@login_required
def create_product():
    form = request.form
    files = request.files
    errors = validate_product_payload(form, files)
    if errors:
        if request.accept_mimetypes.accept_json:
            return json_error("Validation error", errors, 400)
        else:
            categories = Category.query.filter_by(is_active=True).all()
            return render_new_product_form(categories, errors, form)

    current_user = get_current_user()
    if not current_user:
        return json_error("Authentication required", {"auth": ["login_required"]}, 401)

    try:
        new_product = Product(
            name=form['name'].strip(),
            category_id=int(form['category_id']),
            owner_id=current_user.id,
            owner_name=form['owner_name'].strip(),
            description=form['description'].strip(),
            price=form['price'],
            currency=form.get('currency', 'USD'),
            condition=form['condition'],
            warranty_months=int(form.get('warranty_months', 0)),
            delivery_details=form['delivery_details'].strip()
        )
        db.session.add(new_product)
        db.session.flush()  # Get the product ID before committing

        upload_dir = 'static/uploads/products'
        saved_images = save_uploaded_images(files, upload_dir, ['image/jpeg', 'image/png', 'image/webp'], 5, 5242880)
        for idx, image_data in enumerate(saved_images):
            product_image = ProductImage(
                product_id=new_product.id,
                file_path=image_data['file_path'],
                mime_type=image_data['mime_type'],
                file_size_bytes=image_data['file_size_bytes'],
                is_primary=(idx == 0)
            )
            db.session.add(product_image)

        db.session.commit()

        if request.accept_mimetypes.accept_json:
            return json_success({
                "product": {
                    "id": new_product.id,
                    "name": new_product.name,
                    "category_id": new_product.category_id,
                    "owner_id": new_product.owner_id,
                    "owner_name": new_product.owner_name,
                    "description": new_product.description,
                    "price": str(new_product.price),
                    "currency": new_product.currency,
                    "condition": new_product.condition,
                    "warranty_months": new_product.warranty_months,
                    "delivery_details": new_product.delivery_details,
                    "is_active": new_product.is_active,
                    "created_at": new_product.created_at.isoformat(),
                    "images": [{
                        "id": img.id,
                        "file_path": img.file_path,
                        "mime_type": img.mime_type,
                        "file_size_bytes": img.file_size_bytes,
                        "is_primary": img.is_primary
                    } for img in ProductImage.query.filter_by(product_id=new_product.id).all()]
                }
            }, 201)
        else:
            return redirect(url_for('product_dashboard'))

    except Exception as e:
        db.session.rollback()
        return json_error("An error occurred while creating the product", {"db": [str(e)]}, 500)