"""Simple in-memory rate limiter for auth endpoints."""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit POST /api/v1/auth/login to prevent brute-force attacks.

    Limits: 10 requests per 60-second window per IP.
    """

    def __init__(self, app, max_requests: int = 10, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "POST" and request.url.path == "/api/v1/auth/login":
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            cutoff = now - self.window_seconds

            # Prune old entries
            self._hits[client_ip] = [t for t in self._hits[client_ip] if t > cutoff]

            if len(self._hits[client_ip]) >= self.max_requests:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": "Too many login attempts. Please try again later.",
                            "field": None,
                        }
                    },
                )

            self._hits[client_ip].append(now)

        return await call_next(request)
