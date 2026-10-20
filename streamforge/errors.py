from __future__ import annotations

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException


class APIError(Exception):
    """An error that maps cleanly onto a JSON response."""

    def __init__(self, status: int, code: str, message: str, **details):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def to_response(self):
        body = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            body["error"]["details"] = self.details
        return jsonify(body), self.status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def _api_error(err: APIError):
        return err.to_response()

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        # Keep HTML error pages for browser routes, JSON for the API.
        if not request.path.startswith("/api/"):
            return err
        code = (err.name or "error").lower().replace(" ", "_")
        return APIError(err.code or 500, code, err.description or err.name).to_response()

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        app.logger.exception("unhandled error")
        return APIError(500, "internal_error", "Something went wrong.").to_response()
