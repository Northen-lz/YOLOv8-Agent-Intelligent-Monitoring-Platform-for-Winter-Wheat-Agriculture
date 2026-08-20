from ..models.product import Product, db


class ProductService:
    """商品服务 - 与 UserService 存在相似的 CRUD 逻辑（代码重复）"""

    def create(self, name, price, description="", stock=0):
        product = Product(name=name, price=price, description=description, stock=stock)
        db.session.add(product)
        db.session.commit()
        return product

    def get(self, product_id):
        return Product.query.get(product_id)

    def list(self):
        return Product.query.all()

    def update(self, product_id, **fields):
        product = Product.query.get(product_id)
        if not product:
            return None
        for key, value in fields.items():
            if hasattr(product, key):
                setattr(product, key, value)
        db.session.commit()
        return product

    def delete(self, product_id):
        product = Product.query.get(product_id)
        if not product:
            return False
        db.session.delete(product)
        db.session.commit()
        return True
