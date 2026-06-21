import os

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lib.openapi import install_openapi_route

from .blueprint import products_bp
from .db import Base


def create_app(db_url: str | None = None) -> Flask:
    app = Flask(__name__)
    db_url = db_url or os.environ.get(
        "DATABASE_URL", "postgresql://flask_bdd:flask_bdd@localhost:5432/flask_bdd"
    )
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    app.config["SESSION_FACTORY"] = sessionmaker(bind=engine)
    app.register_blueprint(products_bp)
    install_openapi_route(app, title="Products API", version="0.1.0")
    return app
