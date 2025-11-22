"""Core application routes for initial scaffolding."""
from __future__ import annotations

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.get("/health")
def healthcheck() -> tuple[dict[str, str], int]:
    """Simple health endpoint to verify the service is running."""
    return jsonify(status="ok"), 200
