from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from app import db
from models.user import User
from models.view_product_dashboard_product_listing import ProductListing
from models.view_product_dashboard_buy_request import BuyRequest
from models.view_product_dashboard_offer import Offer
from views.view_product_dashboard_views import render_product_dashboard

view_product_dashboard = Blueprint('view_product_dashboard', __name__)

@view_product_dashboard.route('/dashboard/products', methods=['GET'])
def product_dashboard():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    summary = build_dashboard_summary(user.id)
    return render_product_dashboard(summary)

@view_product_dashboard.route('/api/dashboard/products', methods=['GET'])
def product_dashboard_api():
    user = get_current_user()
    if not user:
        return jsonify({"error": "authentication_required"}), 401
    summary = build_dashboard_summary(user.id)
    return jsonify({"summary": summary}), 200

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

def build_dashboard_summary(user_id: int) -> dict:
    products_for_sale = ProductListing.query.filter_by(seller_user_id=user_id).order_by(ProductListing.created_at.desc()).all()
    buy_requests_made = BuyRequest.query.filter_by(buyer_user_id=user_id).order_by(BuyRequest.created_at.desc()).all()
    offers_received = Offer.query.filter_by(seller_user_id=user_id).order_by(Offer.created_at.desc()).all()

    summary = {
        "user_id": user_id,
        "counts": {
            "products_for_sale": len(products_for_sale),
            "buy_requests_made": len(buy_requests_made),
            "offers_received": len(offers_received)
        },
        "lists": {
            "products_for_sale": [{"id": p.id, "title": p.title, "status": p.status, "created_at": p.created_at.isoformat()} for p in products_for_sale],
            "buy_requests_made": [{"id": b.id, "product_listing_id": b.product_listing_id, "product_title": ProductListing.query.get(b.product_listing_id).title, "status": b.status, "created_at": b.created_at.isoformat()} for b in buy_requests_made],
            "offers_received": [{"id": o.id, "product_listing_id": o.product_listing_id, "product_title": ProductListing.query.get(o.product_listing_id).title, "offered_by_user_id": o.offered_by_user_id, "price_cents": o.price_cents, "status": o.status, "created_at": o.created_at.isoformat()} for o in offers_received]
        }
    }
    return summary