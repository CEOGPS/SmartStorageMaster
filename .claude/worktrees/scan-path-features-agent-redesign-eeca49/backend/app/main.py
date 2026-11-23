"""
FastAPI application factory
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # type: ignore[import-not-found]
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse  # type: ignore[import-not-found]
import logging
from contextlib import asynccontextmanager
import asyncio
import os

from .config import get_config
from .db import init_db, create_all_tables, get_session
from .services.scan_service import ScanService, mark_interrupted_scans
from .utils import setup_logging
from .api.routes import scan_routes, cleanup_routes, duplicate_detect_routes, organizer_routes
from .api import usage_routes, duplicate_routes
from .api.routes import compat_routes, agent_routes
from . import api

logger = logging.getLogger(__name__)


def create_app(environment: str = None) -> FastAPI:
    """
    Create and configure FastAPI application
    """
    if environment is None:
        environment = os.getenv('APP_ENV', 'development')

    config = get_config(environment)
    log_level = getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO)
    setup_logging(config.LOG_DIR, log_level)

    logger.info(f"Starting {config.APP_NAME} in {environment} mode")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            init_db(config.DATABASE_URL, config.ECHO_SQL)
            create_all_tables()
            mark_interrupted_scans()
            logger.info("Database initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}", exc_info=True)
            raise
        yield
        logger.info("Application shutting down")

    app = FastAPI(
        title=config.APP_NAME,
        description=config.APP_DESCRIPTION,
        version=config.APP_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(scan_routes.router)
    app.include_router(cleanup_routes.router)
    app.include_router(duplicate_detect_routes.router)
    app.include_router(compat_routes.router)
    app.include_router(usage_routes.router)
    app.include_router(duplicate_routes.router)
    app.include_router(agent_routes.router)
    app.include_router(organizer_routes.router)

    @app.get("/health", tags=["health"])
    def health_check():
        return {"status": "healthy", "app": config.APP_NAME, "version": config.APP_VERSION}

    @app.get("/", tags=["info"])
    def root():
        return {
            "name": config.APP_NAME,
            "version": config.APP_VERSION,
            "description": config.APP_DESCRIPTION,
            "docs": "/docs",
        }

    # WebSocket for scan progress. Pushes the live progress of a scan every
    # 500 ms and sends a final "complete" or "failed" message when it ends.
    # scan_id is optional so a missing query param doesn't 422 the handshake.
    @app.websocket("/ws/scan")
    async def scan_websocket(websocket: WebSocket, scan_id: str = "unknown"):
        await websocket.accept()
        logger.info(f"WebSocket connected for scan {scan_id}")

        def read_progress():
            db = get_session()
            try:
                return ScanService(db).get_progress_snapshot(scan_id)
            finally:
                db.close()

        try:
            while True:
                info = await asyncio.to_thread(read_progress)
                if info is None:
                    await websocket.send_json({"status": "failed", "scan_id": scan_id,
                                               "error_message": "Scan not found"})
                    break

                status = info.get("status")
                message = {
                    "status": "progress",
                    "scan_id": scan_id,
                    "files_found": info.get("files_found", 0),
                    "total_size": info.get("total_size", 0),
                    "percentage": info.get("percentage", 0),
                    "total_estimated": info.get("total_estimated", 0),
                    "potential_savings": info.get("potential_savings", 0),
                    "current_folder": info.get("current_folder", ""),
                    "current_file": info.get("current_file", ""),
                }
                if status == "completed":
                    message["status"] = "completed"
                elif status == "failed":
                    message["status"] = "failed"
                    message["error_message"] = info.get("error_message")
                await websocket.send_json(message)

                if status in ("completed", "failed"):
                    break
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for scan {scan_id}")
        except Exception as e:
            logger.error(f"WebSocket error for scan {scan_id}: {e}", exc_info=True)

    @app.exception_handler(404)
    async def not_found_handler(request, exc):
        return JSONResponse(status_code=404, content={"detail": "Not found", "path": str(request.url.path)})

    logger.info("Application created successfully")
    return app


app = create_app()