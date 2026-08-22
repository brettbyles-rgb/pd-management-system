# Application hosting foundation

The normal local application entry point is now an ASGI application served by
FastAPI and Uvicorn:

```powershell
python -m pd_extractor.web_app
```

Runtime configuration is supplied by the hosting environment:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `PD_MANAGEMENT_DATABASE` | unified local database | Application database path |
| `PD_MANAGEMENT_HOST` | `127.0.0.1` | Listening interface |
| `PD_MANAGEMENT_PORT` | `8766` | Listening port |
| `PD_MANAGEMENT_ENVIRONMENT` | `development` | Environment label in operational logs |
| `PD_MANAGEMENT_LOG_LEVEL` | `INFO` | Logging threshold |
| `PD_MANAGEMENT_MODEL` | current default embedding model | Model configuration |

The application exposes `/health/live` for process liveness and
`/health/ready` for database readiness. Responses include a request ID and
baseline browser security headers. Application request logs are JSON and do
not record request bodies or query-string values.

This is an enterprise-shaped hosting boundary, not an approval to deploy. The
next enterprise controls remain Microsoft Entra ID authentication and role
authorisation, Azure-managed database and file storage, secrets management,
central monitoring, vulnerability scanning, and TAFE NSW environment and
release approval.

`pd_extractor.intelligence_app` remains available temporarily as a rollback
entry point while the ASGI migration is verified.
