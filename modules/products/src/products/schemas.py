from pydantic import BaseModel


class CreateProductRequest(BaseModel):
    name: str
    category: str
    price: float
    stock: int = 0
    active: bool = True


class UpdateProductRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    price: float | None = None


class UpdateStockRequest(BaseModel):
    stock: int = 0


class ProductFilters(BaseModel):
    category: str | None = None
    active: bool | None = None
