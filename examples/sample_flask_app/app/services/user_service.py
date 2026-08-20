from ..models.user import User, db


class UserService:
    """用户服务 - 与 ProductService 存在相似的 CRUD 逻辑（代码重复）"""

    def create(self, username, email, password_hash):
        user = User(username=username, email=email, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()
        return user

    def get(self, user_id):
        return User.query.get(user_id)

    def list(self):
        return User.query.all()

    def update(self, user_id, **fields):
        user = User.query.get(user_id)
        if not user:
            return None
        for key, value in fields.items():
            if hasattr(user, key):
                setattr(user, key, value)
        db.session.commit()
        return user

    def delete(self, user_id):
        user = User.query.get(user_id)
        if not user:
            return False
        db.session.delete(user)
        db.session.commit()
        return True
