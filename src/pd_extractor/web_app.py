from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .career_explorer_reference_data import build_reference_payloads
from .career_explorer_ui import render_career_explorer
from .classifications import classification_rows, seed_classification_references, update_classification_references
from .config import WebSettings, web_settings
from .database import (
    assign_job_family_mappings,
    connect_database,
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


LOGGER = logging.getLogger("pd_management.web")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
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


def _json(value: object, status: int = 200) -> JSONResponse:
    return JSONResponse(value, status_code=status)


def _initialise(settings: WebSettings) -> None:
    with connect_database(settings.database_path) as connection:
        initialise_database(connection)
        seed_classification_references(connection)


def create_app(settings: WebSettings | None = None) -> FastAPI:
    settings = settings or web_settings()

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
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception("request_failed", extra={"request_id": request_id, "path": request.url.path})
            response = _json({"error": "Internal server error", "request_id": request_id}, 500)
        response.headers["X-Request-ID"] = request_id
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        if request.url.path == "/" or request.url.path.endswith("explorer") or response.headers.get("content-type", "").startswith("application/json"):
            response.headers["Cache-Control"] = "no-store"
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
            with connect_database(settings.database_path) as connection:
                connection.execute("SELECT 1").fetchone()
            return {"status": "ready"}
        except Exception:
            return _json({"status": "not_ready"}, 503)

    @app.get("/")
    def home():
        return HTMLResponse(HTML_V2)

    @app.get("/career-explorer")
    def career_explorer():
        with connect_database(settings.database_path) as connection:
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
        with connect_database(settings.database_path) as connection:
            try:
                payload = career_explorer_neighbours(connection, role_id, cursor=cursor, anchored_role_ids=anchored)
            except KeyError:
                return _json({"error": "Role not found"}, 404)
        return _json(payload)

    @app.get("/mapping-assistant")
    def mapping_assistant(request: Request):
        requested_pd = request.query_params.get("pd", "")
        with connect_database(settings.database_path) as connection:
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
        return HTMLResponse(render_mapping_assistant(payload))

    @app.get("/admin/classifications")
    def classification_admin():
        return HTMLResponse(ADMIN_HTML)

    @app.get("/api/version")
    def version():
        return {"version": APP_VERSION, "model": settings.model_name}

    @app.get("/api/classifications")
    def classifications():
        with connect_database(settings.database_path) as connection:
            return {"rows": classification_rows(connection)}

    @app.get("/api/classifications/export")
    def classifications_export(request: Request):
        export_format = request.query_params.get("format", "csv").lower()
        with connect_database(settings.database_path) as connection:
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
        with connect_database(settings.database_path) as connection:
            return {"rows": validation_queue(connection)}

    @app.get("/api/job-family-import-status")
    def get_job_family_import_status():
        with connect_database(settings.database_path) as connection:
            return job_family_import_status(connection)

    @app.get("/api/pds")
    def get_pds(request: Request):
        with connect_database(settings.database_path) as connection:
            return search_pds(connection, request.query_params.get("q", ""))

    @app.get("/api/pds/{pd_id}/intelligence")
    def pd_intelligence(pd_id: int):
        with connect_database(settings.database_path) as connection:
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
        with connect_database(settings.database_path) as connection:
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
        with connect_database(settings.database_path) as connection:
            initialise_database(connection)
            pd_id = import_document(connection, extracted)
            seed_classification_references(connection)
        record = extracted.get("pd_record", {})
        return {"ok": True, "position_description_id": pd_id, "role_title": record.get("role_title", ""), "source_filename": record.get("source_filename", document_path.name), "extraction_status": record.get("extraction_status", ""), "validation_url": f"http://127.0.0.1:8765/?pd={pd_id}"}

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
        with connect_database(settings.database_path) as connection:
            initialise_database(connection)
            summary = import_job_family_workbook(connection, workbook_path)
            count = upsert_embeddings(connection, framework_embedding_sources(connection), _embedder(settings.model_name), model_name=settings.model_name)
            status = job_family_import_status(connection)
        return {"ok": True, "summary": {"import_batch_id": summary.import_batch_id, "framework_rows": summary.framework_rows, "mapping_rows": summary.mapping_rows, "mapping_rows_linked_to_pds": summary.mapping_rows_linked_to_pds, "invalid_mapping_codes": summary.invalid_mapping_codes, "framework_embeddings": count}, "status": status}

    @app.post("/api/pds/{pd_id}/prepare-intelligence")
    def prepare_intelligence(pd_id: int):
        with connect_database(settings.database_path) as connection:
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
        with connect_database(settings.database_path) as connection:
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
        with connect_database(settings.database_path) as connection:
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
    args = parser.parse_args()
    settings = WebSettings(args.database.resolve(), args.model, args.host, args.port, args.environment, args.log_level)
    configure_logging(settings.log_level)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level=settings.log_level.lower(), access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
