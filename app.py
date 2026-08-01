"""Flask application entry point.

Run: flask --app app run --debug
"""
from flask import Flask, jsonify

try:
    from flask_cors import CORS
    _CORS_AVAILABLE = True
except ImportError:
    # flask-cors is in requirements.txt but may be absent in barebones environments
    # (CI sandboxes, container builds without dev deps). Without it we just skip
    # CORS configuration — the app still serves API requests; cross-origin browser
    # requests just won't have the right headers. Print a warning at startup.
    _CORS_AVAILABLE = False

from config import config
from db import close_db, apply_migrations, connect
from routes import users as users_routes
from routes import modules as modules_routes
from routes import majors as majors_routes
from routes import plans as plans_routes
from routes import progress as progress_routes
from routes import recommendations as reco_routes
from routes import study_groups as sg_routes
from routes import scenarios as scenarios_routes
from routes import shares as shares_routes
from routes import badges as badges_routes


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DATABASE_PATH"] = config.DATABASE_PATH

    if _CORS_AVAILABLE:
        CORS(app, origins=config.CORS_ORIGINS, supports_credentials=True)
    else:
        app.logger.warning("flask-cors not installed — CORS headers will not be set. "
                          "Install with `pip install flask-cors` for cross-origin requests.")

    # Apply any un-applied migrations on startup. Idempotent — no-ops if the
    # DB is already current. Failing here (bad migration, disk full, etc.)
    # should abort startup rather than serve requests against half-migrated
    # state; we only catch to log context, then re-raise in production.
    with app.app_context():
        try:
            applied = apply_migrations()
            if applied:
                app.logger.info(f"applied {len(applied)} migration(s): {', '.join(applied)}")
        except Exception as e:
            app.logger.exception(f"migration failure on startup: {e}")
            if not config.auth_dev_mode:
                raise  # in production, don't serve on broken schema

    @app.get("/api/health")
    def health():
        """Liveness/readiness endpoint for load balancers.

        Returns 200 with status info if the app process is up. We also do a
        quick SELECT against schema_migrations as a proxy for "DB is reachable
        and migrations were applied" — if that fails, return 503 so the LB
        removes the instance from rotation.
        """
        try:
            with connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM schema_migrations"
                ).fetchone()
                schema_version = row["n"]
        except Exception as e:
            return jsonify(status="unhealthy", error=str(e)), 503
        return jsonify(
            status="ok",
            auth_mode="dev" if config.auth_dev_mode else "clerk",
            acad_year=config.NUSMODS_ACAD_YEAR,
            schema_version=schema_version,
        )

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="Not found", code="NOT_FOUND"), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception(e)
        return jsonify(error="Internal server error", code="INTERNAL"), 500

    # Blueprints
    app.register_blueprint(users_routes.bp)
    app.register_blueprint(modules_routes.bp)
    app.register_blueprint(majors_routes.bp)
    app.register_blueprint(plans_routes.bp)
    app.register_blueprint(progress_routes.bp)
    app.register_blueprint(reco_routes.bp)
    app.register_blueprint(sg_routes.bp)
    app.register_blueprint(scenarios_routes.bp)
    app.register_blueprint(shares_routes.bp)
    app.register_blueprint(badges_routes.bp)

    app.teardown_appcontext(close_db)

    # ---- CLI ----
    @app.cli.command("sync-modules")
    def sync_modules_cmd():
        """Sync the NUSMods catalogue into the local DB."""
        import click
        from services.nusmods import sync_all
        workers = click.prompt("Workers", default=10, type=int)
        limit = click.prompt("Limit (0 = all)", default=0, type=int)
        success, failures = sync_all(workers=workers, limit=limit or None)
        click.echo(f"\nDone. {success} ok, {len(failures)} failed.")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
