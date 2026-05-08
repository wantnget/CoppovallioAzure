import json

import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger

log = get_logger(__name__)


def main(req: func.HttpRequest) -> func.HttpResponse:
    log.info("request recibido", extra={"endpoint": "/api/api"})

    try:
        validar_api_key(req.headers.get("x-api-key"))
    except AuthError as exc:
        log.warning("auth fallida", extra={"reason": str(exc)})
        return func.HttpResponse(
            json.dumps({"error": str(exc), "code": exc.code}),
            status_code=401,
            mimetype="application/json",
        )

    log.info("auth OK", extra={"auth_result": "ok"})

    return func.HttpResponse(
        json.dumps({"status": "ok", "message": "pong"}),
        status_code=200,
        mimetype="application/json",
    )
