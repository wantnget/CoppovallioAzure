import json

import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger
from shared.blob_loader import save_json_blob_by_id
from shared.supabase_saver import save_identity_supabase

log = get_logger("identidad")

CAMPOS_REQUERIDOS = ("id", "radicado", "tipo_validacion", "status_document", "status_face")

ESTADO_PASO = 1
ESTADO_NO_PASO = 2

MENSAJES_ESTADO = {
    ESTADO_PASO: "Validacion exitosa",
    ESTADO_NO_PASO: "Validacion no aprobada",
}

VALORES_EXITO = {"success", "succes", "ok", "true", "approved", "valid"}
VALORES_FALLO = {"failed", "failure", "fail", "error", "false", "rejected", "invalid"}


def _normalizar_status(valor) -> int:
    if isinstance(valor, bool):
        return ESTADO_PASO if valor else ESTADO_NO_PASO
    if isinstance(valor, (int, float)):
        return ESTADO_PASO if int(valor) == ESTADO_PASO else ESTADO_NO_PASO
    if isinstance(valor, str):
        v = valor.strip().lower()
        if v in VALORES_EXITO or v == str(ESTADO_PASO):
            return ESTADO_PASO
        if v in VALORES_FALLO or v == str(ESTADO_NO_PASO):
            return ESTADO_NO_PASO
    return ESTADO_NO_PASO


def _calcular_estado(status_document: int, status_face: int) -> int:
    return ESTADO_PASO if (status_document == ESTADO_PASO and status_face == ESTADO_PASO) else ESTADO_NO_PASO


def _validar_campos(payload: dict) -> list:
    return [c for c in CAMPOS_REQUERIDOS if payload.get(c) is None]


def _construir_registro(payload: dict) -> tuple:
    status_document = _normalizar_status(payload.get("status_document"))
    status_face = _normalizar_status(payload.get("status_face"))
    estado = _calcular_estado(status_document, status_face)

    registro = {
        "radicado": str(payload.get("radicado")),
        "cedula": str(payload.get("id")),
        "tipo_validacion": payload.get("tipo_validacion"),
        "status_document": status_document,
        "status_face": status_face,
        "estado_validacion": estado,
        "request_json": payload,
    }
    return registro, estado


def main(req: func.HttpRequest) -> func.HttpResponse:
    log.info("request recibido", extra={"endpoint": "/api/identidad"})

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

    registro, estado = _construir_registro(payload)
    cedula = registro["cedula"]
    radicado = registro["radicado"]

    log.info(
        "identidad procesada",
        extra={
            "radicado": radicado,
            "cedula": cedula,
            "status_document": registro["status_document"],
            "status_face": registro["status_face"],
            "estado_validacion": estado,
        },
    )

    out = {
        "status": "ok",
        "estado_validacion": estado,
        "message": MENSAJES_ESTADO[estado],
        "radicado": radicado,
    }

    try:
        save_identity_supabase(radicado, cedula, registro)
        out["_supabase_save"] = "OK"
        log.info("supabase guardado", extra={"radicado": radicado})
    except Exception as exc:
        log.warning("fallo supabase identidad", extra={"radicado": radicado, "error": str(exc)})
        out["_supabase_save"] = f"ERROR: {str(exc)[:200]}"

    try:
        save_json_blob_by_id(cedula, "identidad_output.json", registro)
        out["_blob_save"] = "OK"
        log.info("blob guardado", extra={"cedula": cedula})
    except Exception as exc:
        log.warning("fallo blob identidad", extra={"cedula": cedula, "error": str(exc)})
        out["_blob_save"] = f"ERROR: {str(exc)[:200]}"

    return func.HttpResponse(
        json.dumps(out, ensure_ascii=False, default=str),
        status_code=200,
        mimetype="application/json",
    )
