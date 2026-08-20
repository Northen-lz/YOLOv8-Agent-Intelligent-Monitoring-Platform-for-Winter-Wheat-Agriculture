from flask import Blueprint, jsonify, request

from ..services.order_service import OrderService
from ..services.product_service import ProductService
from ..services.user_service import UserService

api = Blueprint("api", __name__)

user_service = UserService()
product_service = ProductService()
order_service = OrderService()


@api.route("/users", methods=["GET"])
def list_users():
    return jsonify([{"id": u.id, "username": u.username} for u in user_service.list()])


@api.route("/users", methods=["POST"])
def create_user():
    data = request.json
    user = user_service.create(**data)
    return jsonify({"id": user.id}), 201


@api.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = product_service.get(product_id)
    if not product:
        return jsonify({"error": "not found"}), 404
    return jsonify({"id": product.id, "name": product.name})


@api.route("/orders/<int:order_id>/process", methods=["POST"])
def process_order(order_id):
    ok = order_service.process_order(order_id)
    return jsonify({"success": ok})
