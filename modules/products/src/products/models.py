from sqlalchemy import Boolean, Column, Integer, Numeric, String

from .db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "price": float(self.price),
            "stock": self.stock,
            "active": self.active,
        }
