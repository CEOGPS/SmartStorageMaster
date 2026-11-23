"""
Application entry point
"""
import uvicorn
import argparse
import logging
import os

from app.main import create_app

logger = logging.getLogger(__name__)


def main():
    """Run the application"""
    parser = argparse.ArgumentParser(description="Storage Manager Pro API Server")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--env",
        default="development",
        choices=["development", "production", "testing"],
        help="Environment (default: development)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Logging level (default: info)",
    )
    
    args = parser.parse_args()
    
    # Set environment variable for create_app
    os.environ['APP_ENV'] = args.env
    
    # For reload mode, we need to use import string
    if args.reload:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            log_level=args.log_level,
            reload=True,
        )
    else:
        # For non-reload, create app normally
        app = create_app(args.env)
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=args.log_level,
            reload=False,
        )


if __name__ == "__main__":
    main()
