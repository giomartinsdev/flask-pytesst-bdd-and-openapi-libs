from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CreateProductRequest:
    name: str
    category: str
    price: float
    stock: int = 0
    active: bool = True


@dataclass
class UpdateProductRequest:
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None


@dataclass
class UpdateStockRequest:
    stock: int = field(default=0)


@dataclass
class ProductFilters:
    category: Optional[str] = None
    active: Optional[bool] = None
