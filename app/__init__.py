"""Application factory."""
from __future__ import annotations

import os
from flask import Flask, render_template, redirect, url_for
from flask_login import current_user
from dotenv import load_dotenv

from .config import get_config
from .extensions import db, migrate, login_manager, csrf, mail, limiter
from .services.storage import storage_service
from .services.formatting import register_formatting

load_dotenv()


def create_app(config_override: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(get_config())
    if config_override:
        app.config.update(config_override)

    _init_extensions(app)
    _register_blueprints(app)
    _register_cli(app)
    _register_error_handlers(app)
    _register_context(app)
    _register_root_routes(app)
    register_formatting(app)

    return app


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    storage_service.init(app)

    from .models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))


def _register_blueprints(app: Flask) -> None:
    from .blueprints.auth import auth_bp
    from .blueprints.admin import admin_bp
    from .blueprints.company import company_bp
    from .blueprints.member import member_bp
    from .blueprints.booking import booking_bp
    from .blueprints.api import api_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(company_bp, url_prefix="/company")
    app.register_blueprint(member_bp, url_prefix="/me")
    app.register_blueprint(booking_bp, url_prefix="/book")
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    # API blueprint is stateless — exempt from CSRF (uses tokens)
    csrf.exempt(api_bp)


def _register_cli(app: Flask) -> None:
    from .cli import register_cli
    register_cli(app)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500


def _register_context(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        return {
            "app_name": app.config.get("APP_NAME", "CoWorkHub"),
        }


def _register_root_routes(app: Flask) -> None:
    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("auth.post_login_redirect"))
        return render_template("public/landing.html")

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    from flask import send_from_directory, abort as flask_abort

    @app.route("/downloads/<path:key>")
    def local_download(key: str):
        """Local-mode file downloads. Cloud modes use signed URLs and skip this route."""
        if app.config.get("STORAGE_BACKEND") != "local":
            flask_abort(404)
        if not current_user.is_authenticated:
            flask_abort(401)
        return send_from_directory(app.config["LOCAL_STORAGE_DIR"], key, as_attachment=True)
