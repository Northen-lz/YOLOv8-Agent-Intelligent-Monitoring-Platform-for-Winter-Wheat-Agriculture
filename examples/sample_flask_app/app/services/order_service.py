from ..models.order import Order
from ..models.product import Product
from ..models.user import User, db


class OrderService:
    """订单服务"""

    def process_order(self, order_id):
        """处理订单 - 过深嵌套示例（文档 9.6 中的重构目标）"""
        order = Order.query.get(order_id)
        if order:
            if order.status == "pending":
                product = Product.query.get(order.product_id)
                if product:
                    if product.stock >= order.quantity:
                        product.stock -= order.quantity
                        order.status = "processing"
                        db.session.commit()
                        return True
                    else:
                        return False  # 库存不足
                else:
                    return False  # 商品不存在
            else:
                return False  # 订单状态不允许处理
        return False  # 订单不存在

    def get_order(self, order_id):
        return Order.query.get(order_id)

    def get_user_orders(self, user_id):
        user = User.query.get(user_id)
        return user.orders if user else []
