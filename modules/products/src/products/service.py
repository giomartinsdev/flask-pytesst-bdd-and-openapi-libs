from decimal import Decimal
import json

from sqlalchemy.orm import Session

from .models import Product
from .schemas import CreateProductRequest, ProductFilters, UpdateProductRequest


class ProductError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class ProductService:
    def __init__(
        self,
        session: Session,
        sqs_client=None,
        sns_client=None,
        s3_client=None,
        sqs_queue_url: str = "",
        sns_topic_arn: str = "",
        s3_bucket: str = "",
    ):
        self._session = session
        self._sqs = sqs_client
        self._sns = sns_client
        self._s3 = s3_client
        self._queue_url = sqs_queue_url
        self._topic_arn = sns_topic_arn
        self._bucket = s3_bucket

    def create(self, req: CreateProductRequest) -> Product:
        if req.price <= 0:
            raise ProductError("price must be greater than 0")
        if req.stock < 0:
            raise ProductError("stock cannot be negative")
        self._assert_unique_name(req.name, req.category)
        product = Product(
            name=req.name,
            category=req.category,
            price=req.price,
            stock=req.stock,
            active=req.active,
        )
        self._session.add(product)
        self._session.commit()
        self._session.refresh(product)
        self._publish_event("product.created", product)
        return product

    def list_all(self, filters: ProductFilters) -> "list[Product]":
        q = self._session.query(Product)
        if filters.category is not None:
            q = q.filter(Product.category == filters.category)
        if filters.active is not None:
            q = q.filter(Product.active == filters.active)
        return q.all()

    def get(self, product_id: int) -> Product:
        product = self._session.get(Product, product_id)
        if product is None:
            raise ProductError(f"product {product_id} not found", status=404)
        return product

    def update(self, product_id: int, req: UpdateProductRequest) -> Product:
        product = self.get(product_id)
        if req.price is not None and req.price <= 0:
            raise ProductError("price must be greater than 0")
        new_name = req.name if req.name is not None else product.name
        new_category = req.category if req.category is not None else product.category
        if new_name != product.name or new_category != product.category:
            self._assert_unique_name(new_name, new_category, exclude_id=product_id)
        if req.name is not None:
            product.name = req.name
        if req.category is not None:
            product.category = req.category
        if req.price is not None:
            product.price = Decimal(str(req.price))
        self._session.commit()
        self._session.refresh(product)
        return product

    def update_stock(self, product_id: int, stock: int) -> Product:
        if stock < 0:
            raise ProductError("stock cannot be negative")
        product = self.get(product_id)
        product.stock = stock
        self._session.commit()
        self._session.refresh(product)
        if stock == 0:
            self._publish_sns_alert("low_stock", product)
        return product

    def toggle_status(self, product_id: int) -> Product:
        product = self.get(product_id)
        product.active = not product.active
        self._session.commit()
        self._session.refresh(product)
        return product

    def delete(self, product_id: int) -> None:
        product = self.get(product_id)
        if product.stock > 0:
            raise ProductError("cannot delete product with remaining stock")
        self._session.delete(product)
        self._session.commit()
        self._publish_event("product.deleted", product)

    def upload_asset(
        self,
        product_id: int,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self.get(product_id)
        if self._s3 and self._bucket:
            self._s3.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        return key

    def _assert_unique_name(
        self, name: str, category: str, exclude_id: int | None = None
    ) -> None:
        q = self._session.query(Product).filter(
            Product.name == name, Product.category == category
        )
        if exclude_id is not None:
            q = q.filter(Product.id != exclude_id)
        if q.first() is not None:
            raise ProductError(
                f"product '{name}' already exists in category '{category}'"
            )

    def _publish_event(self, event_type: str, product: Product) -> None:
        if self._sqs and self._queue_url:
            self._sqs.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps({"event": event_type, "product_id": product.id}),
            )

    def _publish_sns_alert(self, alert_type: str, product: Product) -> None:
        if self._sns and self._topic_arn:
            self._sns.publish(
                TopicArn=self._topic_arn,
                Message=json.dumps({"alert": alert_type, "product_id": product.id}),
                Subject=alert_type,
            )
