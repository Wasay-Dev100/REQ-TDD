from flask import Blueprint, request, jsonify, render_template
from app import db
from models.product_search_product import ProductSearchProduct
from models.product_search_category import ProductSearchCategory
from sqlalchemy.orm import Query

product_search_bp = Blueprint('product_search', __name__)

@product_search_bp.route('/products/search', methods=['GET'])
def search_products():
    keyword = request.args.get('keyword', '')
    category_id = request.args.get('category_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = build_product_search_query(keyword, category_id)
    total, products = paginate_query(query, page, per_page)

    if not products:
        message = 'No products found'
    else:
        message = ''

    categories = ProductSearchCategory.query.filter_by(is_active=True).all()
    return render_template('product_search_search.html', query=keyword, category_id=category_id, page=page, per_page=per_page, total=total, products=products, message=message, categories=categories)

@product_search_bp.route('/categories', methods=['GET'])
def list_categories():
    categories = ProductSearchCategory.query.filter_by(is_active=True).all()
    return render_template('product_search_categories.html', categories=categories)

@product_search_bp.route('/products', methods=['GET'])
def browse_products():
    category_id = request.args.get('category_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = ProductSearchProduct.query.filter_by(is_active=True)
    if category_id:
        query = query.filter_by(category_id=category_id)

    total, products = paginate_query(query, page, per_page)

    if not products:
        message = 'No products found'
    else:
        message = ''

    categories = ProductSearchCategory.query.filter_by(is_active=True).all()
    return render_template('product_search_browse.html', category_id=category_id, page=page, per_page=per_page, total=total, products=products, message=message, categories=categories)

def normalize_query(raw_query):
    return raw_query.strip().lower()

def build_product_search_query(keyword, category_id):
    query = ProductSearchProduct.query.filter(ProductSearchProduct.is_active == True)
    if keyword:
        query = query.filter(ProductSearchProduct.name.ilike(f'%{normalize_query(keyword)}%'))
    if category_id:
        query = query.filter(ProductSearchProduct.category_id == category_id)
    return query

def paginate_query(query, page, per_page):
    pagination = query.paginate(page, per_page, error_out=False)
    return pagination.total, pagination.items