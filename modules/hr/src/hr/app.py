import os

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hr.api.areas.blueprint import areas_bp
from hr.api.employees.blueprint import employees_bp
from hr.db import Base
from lib.openapi import install_openapi_route


def create_app(db_url: str | None = None) -> Flask:
    app = Flask(__name__)
    db_url = db_url or os.environ.get(
        "DATABASE_URL", "mssql+pymssql://SA:BddTest1!@localhost:1433/tempdb"
    )
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    app.config["SESSION_FACTORY"] = sessionmaker(bind=engine)
    app.register_blueprint(employees_bp)
    app.register_blueprint(areas_bp)
    install_openapi_route(app, title="HR API", version="0.1.0")
    return app
