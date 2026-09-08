from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from .career_explorer_reference_data import build_reference_payloads
from .career_explorer_ui import render_career_explorer
from .classifications import classification_rows, seed_classification_references, update_classification_references
from .config import WebSettings, web_settings
from .database import (
    assign_job_family_mappings,
    connect_database,
    database_object_exists,
    import_document,
    initialise_database,
    job_family_mappings_for_pd,
)
from .embeddings import framework_embedding_sources, upsert_embeddings
from .extractor import extract_document
from .intelligence_app import (
    ADMIN_HTML,
    APP_VERSION,
    HTML_V2,
    _classification_backup_path,
    _classifications_csv,
    _embedder,
    _safe_docx_filename,
    _safe_workbook_filename,
    _similar_json,
    _to_jsonable,
    _uploaded_job_family_path,
    _uploaded_pd_path,
    career_explorer_neighbours,
    job_family_import_status,
    pd_detail,
    resolve_pd_identifier,
    search_pds,
    validation_queue,
    render_application_shell,
    render_classification_admin,
)
from .intelligence_prepare import prepare_pd_intelligence
from .job_family_import import import_job_family_workbook
from .mapping_assistant_ui import build_mapping_assistant_payload, render_mapping_assistant
from .mapping_suggestions import (
    framework_similarity_scores_for_pd,
    framework_similarity_scores_for_query,
    suggest_mappings_for_pd,
    suggest_mappings_for_query,
)
from .similarity import find_similar_roles, search_roles
from .validation_app import (
    confirm_validation,
    get_validated_export,
    get_validation_record,
    list_validation_records,
    render_validation_app,
    save_validation_draft,
)


LOGGER = logging.getLogger("pd_management.web")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
EXPLORER_DEMO_PATHS = {
    "/",
    "/career-explorer",
    "/api/career-explorer/neighbours",
    "/api/version",
    "/health/live",
    "/health/ready",
}
POC_PUBLIC_PATHS = {
    "/career-explorer",
    "/api/career-explorer/neighbours",
    "/health/live",
    "/health/ready",
}
POC_DISABLED_PATHS = {
    # The hosted PoC intentionally omits the local ML runtime. Stored similarity
    # data remains readable, but free-text searches requiring a live model do not.
    "/api/search",
}


class JsonFormatter(logging.Formatter):
    """Emit machine-readable operational logs without request content or query data."""

    def format(self, record: logging.LogRecord) -> str:
        event = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in ("environment", "request_id", "method", "path", "status", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                event[field] = value
        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)
        return json.dumps(event, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.setLevel(level.upper())
    LOGGER.propagate = False


def _safe_exception_summary(error: Exception) -> str:
    """Return useful diagnostics without emitting configured database credentials."""
    detail = str(error)
    for variable in ("PGPASSWORD", "PD_MANAGEMENT_ADMIN_PASSWORD"):
        secret = os.environ.get(variable, "")
        if secret:
            detail = detail.replace(secret, "[redacted]")
    detail = re.sub(
        r"(?i)(postgres(?:ql)?://[^:/\s]+:)[^@\s]+(@)",
        r"\1[redacted]\2",
        detail,
    )
    return " ".join(detail.split())[:1000] or "no error message"


def _json(value: object, status: int = 200) -> JSONResponse:
    return JSONResponse(value, status_code=status)


def _valid_basic_credentials(request: Request, settings: WebSettings) -> bool:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return bool(
        settings.admin_username
        and settings.admin_password
        and secrets.compare_digest(username, settings.admin_username)
        and secrets.compare_digest(password, settings.admin_password)
    )


def _basic_challenge() -> JSONResponse:
    return JSONResponse(
        {"error": "Authentication required"},
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="PD Management PoC", charset="UTF-8"'},
    )


def _initialise(settings: WebSettings) -> None:
    if settings.database_url:
        # Cloud schemas are changed only by the explicit migration command.
        return
    with _connect(settings) as connection:
        initialise_database(connection)
        seed_classification_references(connection)


def _connect(settings: WebSettings):
    return connect_database(
        settings.database_path,
        settings.database_url,
        read_only=settings.deployment_profile in {"explorer-demo", "admin-poc-readonly"},
    )


def _validate_settings(settings: WebSettings) -> None:
    if settings.deployment_profile not in {"full", "explorer-demo", "admin-poc-readonly"}:
        raise ValueError(
            "PD_MANAGEMENT_DEPLOYMENT_PROFILE must be 'full', 'explorer-demo' "
            "or 'admin-poc-readonly'"
        )
    if settings.database_url:
        if not settings.database_url.lower().startswith(("postgresql://", "postgres://")):
            raise ValueError("PD_MANAGEMENT_DATABASE_URL must be a PostgreSQL connection URL")
        if settings.deployment_profile not in {"explorer-demo", "admin-poc-readonly"}:
            raise ValueError(
                "PostgreSQL is currently restricted to read-only deployment profiles"
            )
    if settings.deployment_profile == "admin-poc-readonly" and not (
        settings.admin_username and settings.admin_password
    ):
        raise ValueError(
            "admin-poc-readonly requires PD_MANAGEMENT_ADMIN_USERNAME and "
            "PD_MANAGEMENT_ADMIN_PASSWORD"
        )


def _database_is_ready(settings: WebSettings) -> bool:
    with _connect(settings) as connection:
        connection.execute("SELECT 1").fetchone()
        if settings.require_data:
            row = connection.execute(
                "SELECT COUNT(*) AS role_count FROM position_descriptions"
            ).fetchone()
            count = int(row["role_count"])
            if count < 1 or not database_object_exists(connection, "role_neighbours"):
                return False
    return True


def create_app(settings: WebSettings | None = None) -> FastAPI:
    settings = settings or web_settings()
    _validate_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _initialise(settings)
        LOGGER.info("application_started", extra={"environment": settings.environment})
        yield
        LOGGER.info("application_stopped")

    app = FastAPI(
        title="PD Management System",
        version=APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def operational_controls(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:128]
        started = time.perf_counter()
        if (
            settings.deployment_profile == "explorer-demo"
            and (
                request.method != "GET"
                or request.url.path not in EXPLORER_DEMO_PATHS
            )
        ):
            response = _json({"error": "Not found"}, 404)
        elif settings.deployment_profile == "admin-poc-readonly" and (
            request.url.path not in POC_PUBLIC_PATHS
        ):
            if not _valid_basic_credentials(request, settings):
                response = _basic_challenge()
            elif request.method != "GET":
                response = _json({"error": "Hosted administration is read-only"}, 405)
            elif request.url.path in POC_DISABLED_PATHS:
                response = _json(
                    {"error": "Semantic search is disabled in the hosted PoC"}, 503
                )
            else:
                try:
                    response = await call_next(request)
                except Exception as error:
                    LOGGER.exception(
                        "request_failed: %s: %s",
                        type(error).__name__,
                        _safe_exception_summary(error),
                        extra={"request_id": request_id, "path": request.url.path},
                    )
                    response = _json(
                        {"error": "Internal server error", "request_id": request_id}, 500
                    )
        else:
            try:
                response = await call_next(request)
            except Exception as error:
                LOGGER.exception(
                    "request_failed: %s: %s",
                    type(error).__name__,
                    _safe_exception_summary(error),
                    extra={"request_id": request_id, "path": request.url.path},
                )
                response = _json({"error": "Internal server error", "request_id": request_id}, 500)
        response.headers["X-Request-ID"] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        protected_poc_response = (
            settings.deployment_profile == "admin-poc-readonly"
            and request.url.path not in POC_PUBLIC_PATHS
        )
        if request.url.path == "/" or request.url.path.endswith("explorer") or response.headers.get("content-type", "").startswith("application/json") or protected_poc_response:
            response.headers["Cache-Control"] = "no-store"
        if protected_poc_response:
            response.headers["Vary"] = "Authorization"
        LOGGER.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response

    @app.get("/health/live")
    def health_live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def health_ready():
        try:
            if _database_is_ready(settings):
                return {"status": "ready"}
            return _json({"status": "not_ready"}, 503)
        except Exception:
            return _json({"status": "not_ready"}, 503)

    @app.get("/")
    def home():
        if settings.deployment_profile == "explorer-demo":
            return RedirectResponse("/career-explorer", status_code=302)
        return HTMLResponse(
            render_application_shell(
                read_only=settings.deployment_profile == "admin-poc-readonly"
            )
        )

    @app.get("/career-explorer")
    def career_explorer():
        with _connect(settings) as connection:
            route_payload, constellation_payload = build_reference_payloads(connection)
        return HTMLResponse(render_career_explorer(route_payload, constellation_payload))

    @app.get("/api/career-explorer/neighbours")
    def neighbours(request: Request):
        role_id = request.query_params.get("role_id", "").strip()
        try:
            cursor = int(request.query_params.get("cursor", "0"))
        except ValueError:
            return _json({"error": "cursor must be an integer"}, 400)
        anchored = tuple(item.strip() for value in request.query_params.getlist("anchored") for item in value.split(",") if item.strip())
        with _connect(settings) as connection:
            try:
                payload = career_explorer_neighbours(connection, role_id, cursor=cursor, anchored_role_ids=anchored)
            except KeyError:
                return _json({"error": "Role not found"}, 404)
        return _json(payload)

    @app.get("/mapping-assistant")
    def mapping_assistant(request: Request):
        requested_pd = request.query_params.get("pd", "")
        with _connect(settings) as connection:
            pd_id = resolve_pd_identifier(connection, requested_pd)
            if pd_id is None:
                return RedirectResponse("/#mapping", status_code=302)
            detail = pd_detail(connection, pd_id)
            if detail is None:
                return _json({"error": "Not found"}, 404)
            similar = find_similar_roles(connection, pd_id, model_name=settings.model_name, limit=50)
            scores = framework_similarity_scores_for_pd(connection, pd_id, model_name=settings.model_name)
            payload = build_mapping_assistant_payload(
                connection, detail, job_family_mappings_for_pd(connection, pd_id), _similar_json(connection, similar), scores
            )
        return HTMLResponse(
            render_mapping_assistant(
                payload,
                read_only=settings.deployment_profile == "admin-poc-readonly",
            )
        )

    @app.get("/admin/classifications")
    def classification_admin():
        return HTMLResponse(
            render_classification_admin(
                read_only=settings.deployment_profile == "admin-poc-readonly"
            )
        )

    @app.get("/validation")
    def validation_workspace():
        return HTMLResponse(
            render_validation_app(
                read_only=settings.deployment_profile == "admin-poc-readonly"
            )
        )

    @app.get("/api/validation/pds")
    def validation_records():
        with _connect(settings) as connection:
            return list_validation_records(connection)

    @app.get("/api/validation/pds/{pd_id}")
    def validation_record(pd_id: int):
        with _connect(settings) as connection:
            record = get_validation_record(connection, pd_id)
        return record if record is not None else _json({"error": "Not found"}, 404)

    @app.get("/api/validation/pds/{pd_id}/export")
    def validation_export(pd_id: int, request: Request):
        with _connect(settings) as connection:
            export = get_validated_export(connection, pd_id)
        if export is None:
            return _json({"error": "This PD has not been validated"}, 409)
        filename = Path(
            export.get("pd_record", {}).get("source_filename", f"pd-{pd_id}")
        ).stem
        disposition = "inline" if request.query_params.get("view") == "1" else "attachment"
        return JSONResponse(
            export,
            headers={
                "Content-Disposition": (
                    f'{disposition}; filename="{filename}-validated.json"'
                )
            },
        )

    @app.get("/validation/source/{filename:path}")
    def validation_source(filename: str):
        safe_name = Path(filename).name
        candidates = (
            settings.database_path.parent / "uploaded-pds" / safe_name,
            Path.cwd() / "samples" / safe_name,
            Path(__file__).resolve().parents[2] / "samples" / safe_name,
        )
        source = next((candidate for candidate in candidates if candidate.is_file()), None)
        if source is None:
            return _json({"error": "Source document not available"}, 404)
        return FileResponse(source, filename=source.name, content_disposition_type="inline")

    @app.put("/api/validation/pds/{pd_id}/draft")
    async def validation_save_draft(pd_id: int, request: Request):
        payload = await request.json()
        try:
            with _connect(settings) as connection:
                save_validation_draft(
                    connection,
                    pd_id,
                    payload["draft"],
                    payload.get("section_statuses", {}),
                    payload.get("edited_paths", []),
                )
        except (KeyError, TypeError, ValueError) as error:
            return _json({"error": str(error)}, 400)
        return {"ok": True}

    @app.post("/api/validation/pds/{pd_id}/confirm")
    async def validation_confirm(pd_id: int, request: Request):
        payload = await request.json()
        try:
            with _connect(settings) as connection:
                errors = confirm_validation(
                    connection,
                    pd_id,
                    payload["draft"],
                    payload.get("section_statuses", {}),
                    payload.get("edited_paths", []),
                )
        except (KeyError, TypeError, ValueError) as error:
            return _json({"error": str(error)}, 400)
        return _json({"ok": not errors, "errors": errors}, 200 if not errors else 400)

    @app.post("/api/validation/pds/{pd_id}/prepare-intelligence")
    def validation_prepare_intelligence(pd_id: int):
        with _connect(settings) as connection:
            record = get_validation_record(connection, pd_id)
            if record is None:
                return _json({"error": "Not found"}, 404)
            if record["validation_status"] != "Validated":
                return _json(
                    {"error": "Validate the PD before preparing it for Mapping Assistant"},
                    409,
                )
            summary = prepare_pd_intelligence(
                connection,
                pd_id,
                _embedder(settings.model_name),
                model_name=settings.model_name,
            )
        return {"ok": True, "summary": summary}

    @app.get("/api/version")
    def version():
        return {"version": APP_VERSION, "model": settings.model_name}

    @app.get("/api/classifications")
    def classifications():
        with _connect(settings) as connection:
            return {"rows": classification_rows(connection)}

    @app.get("/api/classifications/export")
    def classifications_export(request: Request):
        export_format = request.query_params.get("format", "csv").lower()
        with _connect(settings) as connection:
            rows = classification_rows(connection)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if export_format == "json":
            body = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            filename, content_type = f"classification-references-{stamp}.json", "application/json; charset=utf-8"
        else:
            body = _classifications_csv(rows)
            filename, content_type = f"classification-references-{stamp}.csv", "text/csv; charset=utf-8"
        return Response(body, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/validation-queue")
    def get_validation_queue():
        with _connect(settings) as connection:
            return {"rows": validation_queue(connection)}

    @app.get("/api/job-family-import-status")
    def get_job_family_import_status():
        with _connect(settings) as connection:
            return job_family_import_status(connection)

    @app.get("/api/pds")
    def get_pds(request: Request):
        with _connect(settings) as connection:
            return search_pds(connection, request.query_params.get("q", ""))

    @app.get("/api/pds/{pd_id}/intelligence")
    def pd_intelligence(pd_id: int):
        with _connect(settings) as connection:
            detail = pd_detail(connection, pd_id)
            if detail is None:
                return _json({"error": "Not found"}, 404)
            similar = find_similar_roles(connection, pd_id, model_name=settings.model_name, limit=50)
            suggestions = suggest_mappings_for_pd(connection, pd_id, model_name=settings.model_name)
            scores = framework_similarity_scores_for_pd(connection, pd_id, model_name=settings.model_name)
            assigned = job_family_mappings_for_pd(connection, pd_id)
            similar_json = _similar_json(connection, similar)
        return {"pd": detail, "assigned_mappings": assigned, "similar_roles": similar_json, "mapping_suggestions": _to_jsonable(suggestions), "framework_scores": scores}

    @app.get("/api/search")
    def semantic_search(request: Request):
        query = request.query_params.get("query", "").strip()
        if not query:
            return _json({"error": "Missing query"}, 400)
        with _connect(settings) as connection:
            model = _embedder(settings.model_name)
            roles = search_roles(connection, query, model, model_name=settings.model_name, limit=50)
            suggestions = suggest_mappings_for_query(connection, query, model, model_name=settings.model_name)
            scores = framework_similarity_scores_for_query(connection, query, model, model_name=settings.model_name)
            roles_json = _similar_json(connection, roles)
        return {"query": query, "roles": roles_json, "mapping_suggestions": _to_jsonable(suggestions), "framework_scores": scores}

    @app.post("/api/import-pd")
    async def import_pd(request: Request):
        payload = await request.json()
        if not isinstance(payload, dict):
            return _json({"error": "Invalid upload payload"}, 400)
        filename = _safe_docx_filename(str(payload.get("filename") or ""))
        encoded = str(payload.get("content_base64") or "")
        if not encoded:
            return _json({"error": "No file content supplied"}, 400)
        document_path = _uploaded_pd_path(settings.database_path, filename)
        document_path.write_bytes(base64.b64decode(encoded))
        extracted = extract_document(document_path)
        with _connect(settings) as connection:
            initialise_database(connection)
            pd_id = import_document(connection, extracted)
            seed_classification_references(connection)
        record = extracted.get("pd_record", {})
        return {"ok": True, "position_description_id": pd_id, "role_title": record.get("role_title", ""), "source_filename": record.get("source_filename", document_path.name), "extraction_status": record.get("extraction_status", ""), "validation_url": f"/validation?pd={pd_id}"}

    @app.post("/api/import-job-family-workbook")
    async def import_job_family(request: Request):
        payload = await request.json()
        if not isinstance(payload, dict):
            return _json({"error": "Invalid upload payload"}, 400)
        filename = _safe_workbook_filename(str(payload.get("filename") or ""))
        encoded = str(payload.get("content_base64") or "")
        if not encoded:
            return _json({"error": "No file content supplied"}, 400)
        workbook_path = _uploaded_job_family_path(settings.database_path, filename)
        workbook_path.write_bytes(base64.b64decode(encoded))
        with _connect(settings) as connection:
            initialise_database(connection)
            summary = import_job_family_workbook(connection, workbook_path)
            count = upsert_embeddings(connection, framework_embedding_sources(connection), _embedder(settings.model_name), model_name=settings.model_name)
            status = job_family_import_status(connection)
        return {"ok": True, "summary": {"import_batch_id": summary.import_batch_id, "framework_rows": summary.framework_rows, "mapping_rows": summary.mapping_rows, "mapping_rows_linked_to_pds": summary.mapping_rows_linked_to_pds, "invalid_mapping_codes": summary.invalid_mapping_codes, "framework_embeddings": count}, "status": status}

    @app.post("/api/pds/{pd_id}/prepare-intelligence")
    def prepare_intelligence(pd_id: int):
        with _connect(settings) as connection:
            initialise_database(connection)
            if pd_detail(connection, pd_id) is None:
                return _json({"error": "Not found"}, 404)
            summary = prepare_pd_intelligence(connection, pd_id, _embedder(settings.model_name), model_name=settings.model_name)
        return {"ok": True, "summary": summary}

    @app.post("/api/pds/{pd_id}/assign-mappings")
    async def assign_mappings(pd_id: int, request: Request):
        payload = await request.json()
        codes = payload.get("mapping_codes", []) if isinstance(payload, dict) else []
        if not isinstance(codes, list):
            return _json({"error": "mapping_codes must be a list"}, 400)
        rationale = str(payload.get("rationale") or "").strip() if isinstance(payload, dict) else ""
        notes = f"Assigned in Mapping Assistant. Rationale: {rationale}" if rationale else "Assigned in Mapping Assistant"
        with _connect(settings) as connection:
            initialise_database(connection)
            try:
                mappings = assign_job_family_mappings(connection, pd_id, codes, validation_notes=notes)
            except KeyError:
                return _json({"error": "PD not found"}, 404)
            except ValueError as exc:
                return _json({"error": str(exc)}, 400)
        return {"ok": True, "mappings": mappings}

    @app.put("/api/classifications")
    async def put_classifications(request: Request):
        payload = await request.json()
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        with _connect(settings) as connection:
            before = classification_rows(connection)
            _classification_backup_path(settings.database_path).write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
            updated = update_classification_references(connection, rows)
        return {"updated": updated}

    return app


app = create_app()


def main() -> int:
    defaults = web_settings()
    parser = argparse.ArgumentParser(description="Run the PD Management ASGI application")
    parser.add_argument("--database", type=Path, default=defaults.database_path)
    parser.add_argument("--model", default=defaults.model_name)
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)
    parser.add_argument("--environment", default=defaults.environment)
    parser.add_argument("--log-level", default=defaults.log_level)
    parser.add_argument(
        "--deployment-profile",
        choices=("full", "explorer-demo", "admin-poc-readonly"),
        default=defaults.deployment_profile,
    )
    parser.add_argument("--require-data", action="store_true", default=defaults.require_data)
    args = parser.parse_args()
    settings = WebSettings(
        args.database.resolve(),
        args.model,
        args.host,
        args.port,
        args.environment,
        args.log_level,
        args.deployment_profile,
        args.require_data,
        defaults.database_url,
        defaults.admin_username,
        defaults.admin_password,
    )
    configure_logging(settings.log_level)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level=settings.log_level.lower(), access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
