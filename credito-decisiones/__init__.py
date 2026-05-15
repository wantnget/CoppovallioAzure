import json

import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger
from shared.blob_loader import save_json_blob_by_id
from shared.supabase_saver import save_credito_decision_supabase

log = get_logger("credito_decision")

CAMPOS_REQUERIDOS = ("radicado", "cedula", "opcion_elegida")
OPCIONES_VALIDAS = {"B1", "B2", "B3"}


def _normalizar_opcion(valor) -> str | None:
    if not isinstance(valor, str):
        return None
    v = valor.strip().upper()
    return v if v in OPCIONES_VALIDAS else None


def _validar_campos(payload: dict) -> list:
    return [c for c in CAMPOS_REQUERIDOS if payload.get(c) is None]


def main(req: func.HttpRequest) -> func.HttpResponse:
    log.info("request recibido", extra={"endpoint": "/api/credito_decision"})

    try:
        validar_api_key(req.headers.get("x-api-key"))
    except AuthError as exc:
        log.warning("auth fallida", extra={"reason": str(exc)})
        return func.HttpResponse(
            json.dumps({"error": str(exc), "code": exc.code}),
            status_code=401,
            mimetype="application/json",
        )

    try:
        payload = req.get_json()
    except ValueError:
        log.warning("body JSON invalido")
        return func.HttpResponse(
            json.dumps({"error": "Body JSON inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    faltantes = _validar_campos(payload)
    if faltantes:
        log.warning("campos faltantes", extra={"campos": faltantes})
        return func.HttpResponse(
            json.dumps({"error": f"Campos requeridos faltantes: {faltantes}"}),
            status_code=400,
            mimetype="application/json",
        )

    radicado = str(payload.get("radicado"))
    cedula = str(payload.get("cedula"))
    opcion_elegida = _normalizar_opcion(payload.get("opcion_elegida"))

    if opcion_elegida is None:
        log.warning("opcion_elegida invalida", extra={
                    "valor": payload.get("opcion_elegida")})
        return func.HttpResponse(
            json.dumps(
                {"error": f"opcion_elegida debe ser una de: {sorted(OPCIONES_VALIDAS)}"}),
            status_code=400,
            mimetype="application/json",
        )

    log.info(
        "decision procesada",
        extra={
            "radicado": radicado,
            "cedula": cedula,
            "opcion_elegida": opcion_elegida,
        },
    )

    out = {
        "status": "ok",
        "message": "Decision registrada",
        "radicado": radicado,
        "opcion_elegida": opcion_elegida,
    }

    registro = {
        "radicado": radicado,
        "opcion_elegida": opcion_elegida,
        "response": dict(out),
    }

    try:
        save_credito_decision_supabase(radicado, registro)
        out["_supabase_save"] = "OK"
        log.info("supabase guardado", extra={"radicado": radicado})
    except Exception as exc:
        log.warning("fallo supabase credito_decision", extra={
                    "radicado": radicado, "error": str(exc)})
        out["_supabase_save"] = f"ERROR: {str(exc)[:200]}"

    try:
        save_json_blob_by_id(cedula, "credito_decision_output.json", registro)
        out["_blob_save"] = "OK"
        log.info("blob guardado", extra={"cedula": cedula})
    except Exception as exc:
        log.warning("fallo blob credito_decision", extra={
                    "cedula": cedula, "error": str(exc)})
        out["_blob_save"] = f"ERROR: {str(exc)[:200]}"

    return func.HttpResponse(
        json.dumps(out, ensure_ascii=False, default=str),
        status_code=200,
        mimetype="application/json",
    )
