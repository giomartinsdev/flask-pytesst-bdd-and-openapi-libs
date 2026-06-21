import os
from typing import Optional
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .db import Base
from .blueprint import hr_bp
from . import models  # noqa: F401 — registers Employee with Base


def create_app(db_url: Optional[str] = None) -> Flask:
    app = Flask(__name__)
    db_url = db_url or os.environ.get(
        "DATABASE_URL", "postgresql://flask_bdd:flask_bdd@localhost:5432/flask_bdd"
    )
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    app.config["SESSION_FACTORY"] = sessionmaker(bind=engine)
    app.register_blueprint(hr_bp)
    return app
