from __future__ import annotations

from pathlib import Path

from flask import Flask

from . import auth, documents, search
from .config import Config
from .extensions import db
from .security import init_auth_manager
from .models import SearchIndex, load_user


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    manager = init_auth_manager(app)
    manager.login_view = "auth.login"
    manager.login_message_category = "warning"
    manager.user_loader(load_user)

    register_blueprints(app)
    register_cli(app)

    with app.app_context():
        db.create_all()

    return app


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth.bp)
    app.register_blueprint(documents.bp)
    app.register_blueprint(search.bp)


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    def create_admin() -> None:
        """Create an administrator account."""
        from getpass import getpass

        from .models import Role, User

        username = input("Username: ")
        if not username:
            raise SystemExit("Username is required")
        password = getpass("Password: ")
        confirm = getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")

        user = User.query.filter_by(username=username).first()
        if user:
            print("User already exists.")
            return

        user = User(username=username, role=Role.ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print("Administrator created.")

    @app.cli.command("reindex")
    def rebuild_index() -> None:
        from .models import Document

        SearchIndex.query.delete()
        for document in Document.query.all():
            SearchIndex.rebuild_for_document(document)
        db.session.commit()
        print("Search index rebuilt.")

    @app.cli.command("init-db")
    def init_db() -> None:
        """Explicitly create the SQLite schema."""

        db.create_all()
        print("Database initialized.")
