from flask import Blueprint, jsonify, abort
from app import db
from models.product import Product
from models.user import User
from models.category import Category
from views.view_product_details_views import render_product_details_page

view_product_details_bp = Blueprint("view_product_details", __name__)


@view_product_details_bp.route("/products/<int:product_id>", methods=["GET"])
def view_product_details(product_id):
    product = fetch_product_or_404(product_id)
    product_details = build_product_details_dto(product)
    return render_product_details_page(product_details)


@view_product_details_bp.route("/api/products/<int:product_id>", methods=["GET"])
def get_product_details_api(product_id):
    product = fetch_product_or_404(product_id)
    product_details = build_product_details_dto(product)
    return jsonify(product_details), 200


def fetch_product_or_404(product_id):
    product = Product.query.filter_by(id=product_id).first()
    if not product or not bool(product.is_active):
        abort(404)
    return product


def build_product_details_dto(product):
    category = Category.query.filter_by(id=product.category_id).first()
    seller = User.query.filter_by(id=product.seller_id).first()

    if not category or not seller:
        abort(404)

    def _dec_to_str(val):
        if val is None:
            return None
        try:
            return format(val, "f")
        except Exception:
            return str(val)

    return {
        "product_id": int(product.id),
        "general": {
            "name": product.name or "",
            "sku": product.sku or "",
            "category": {
                "id": int(category.id),
                "name": category.name or "",
                "slug": category.slug or "",
            },
            "brand": product.brand,
            "model_number": product.model_number,
            "condition": product.condition or "",
            "is_active": bool(product.is_active),
        },
        "seller": {
            "id": int(seller.id),
            "username": seller.username or "",
            "email": seller.email or "",
        },
        "description": {
            "short_description": product.short_description or "",
            "full_description": product.description or "",
            "weight_kg": _dec_to_str(product.weight_kg),
            "dimensions_cm": product.dimensions_cm,
        },
        "pricing": {
            "currency": product.currency or "",
            "list_price": _dec_to_str(product.list_price),
            "sale_price": _dec_to_str(product.sale_price),
            "effective_price": _dec_to_str(product.get_effective_price()),
            "stock_quantity": int(product.stock_quantity or 0),
        },
        "delivery": {
            "method": product.delivery_method or "",
            "fee": _dec_to_str(product.delivery_fee),
            "estimated_min_days": int(product.delivery_estimated_min_days or 0),
            "estimated_max_days": int(product.delivery_estimated_max_days or 0),
            "ships_from": product.ships_from,
            "return_policy": product.return_policy,
        },
        "warranty": {
            "type": product.warranty_type or "",
            "period_months": product.warranty_period_months,
            "details": product.warranty_details,
        },
    }