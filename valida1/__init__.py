import json
import os
from datetime import datetime

import requests
import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger
from shared.blob_loader import save_json_blob_by_id

log = get_logger("valida1")

TIMEOUT = 15


def generar_radicado(cedula: str) -> str:
    return f"{cedula}_{datetime.now().strftime('%d%m%y%H%M%S')}"


def consultar_coopvalili(cedula: str) -> dict | None:
    base_url = os.environ.get("COOPVALILI_URL", "")
    token = os.environ.get("COOPVALILI_TOKEN", "")

    url = f"{base_url}/{cedula}"
    headers = {"X-Auth-Token": token}

    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=True)
        log.info("consulta coopvalili", extra={
                 "cedula": cedula, "status": resp.status_code})
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        log.error("fallo consulta coopvalili", extra={
                  "cedula": cedula, "error": str(e)})
        return None
    except ValueError as e:
        log.error("respuesta no es JSON", extra={
                  "cedula": cedula, "error": str(e)})
        return None


def usuario_tiene_datos(data_api: dict | None) -> bool:
    if not data_api or not isinstance(data_api, dict):
        return False
    lista = data_api.get("asociadoList")
    if not lista or not isinstance(lista, list):
        return False
    asociado = lista[0] if lista else None
    if not isinstance(asociado, dict):
        return False
    nombre = asociado.get("nombre", "")
    apellido = asociado.get("primer_apellido", "")
    return bool(str(nombre).strip() and str(apellido).strip())


def procesar_solicitud(payload: dict) -> dict:
    cedula = payload.get("id")
    if not cedula:
        return {"valida1": 2, "radicado": None, "mensaje": "Campo 'id' requerido", "datos": None}

    radicado = generar_radicado(str(cedula))
    data_api = consultar_coopvalili(str(cedula))

    if usuario_tiene_datos(data_api):
        valida1, mensaje = 1, "Usuario encontrado en Coopvalili"
    else:
        valida1, mensaje = 2, "Usuario sin datos en Coopvalili"

    return {
        "radicado": radicado,
        "valida1": valida1,
        "mensaje": mensaje,
        "datos_chat": {
            "id": cedula,
            "salario": payload.get("salario"),
            "tipoSalario": payload.get("tipoSalario"),
            "egresosVolante": payload.get("egresosVolante"),
            "frecuenciaPagos": payload.get("frecuenciaPagos"),
            "lineaCredito": payload.get("lineaCredito"),
            "monto": payload.get("monto"),
            "personasCargo": payload.get("personasCargo"),
        },
        "datos_api": data_api if valida1 == 1 else None,
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    log.info("request recibido", extra={"endpoint": "/api/valida1"})

    # Auth
    try:
        validar_api_key(req.headers.get("x-api-key"))
    except AuthError as exc:
        log.warning("auth fallida", extra={"reason": str(exc)})
        return func.HttpResponse(
            json.dumps({"error": str(exc), "code": exc.code}),
            status_code=401,
            mimetype="application/json",
        )

    # Parsear body
    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body JSON inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    # Lógica principal
    try:
        valida_out = procesar_solicitud(payload)
    except Exception as exc:
        log.error("error en procesar_solicitud", extra={"error": str(exc)})
        return func.HttpResponse(
            json.dumps({"error": "Error interno del servidor"}),
            status_code=500,
            mimetype="application/json",
        )

    cedula = str(payload.get("id", "sin_cedula"))

    # Guardar en Blob (sin romper la respuesta si falla)
    try:
        save_json_blob_by_id(cedula, "valida_output.json", valida_out)
        valida_out["_blob_save"] = "OK"
        log.info("blob guardado", extra={"cedula": cedula})
    except Exception as exc:
        log.warning("fallo blob", extra={"cedula": cedula, "error": str(exc)})
        valida_out["_blob_save"] = f"ERROR: {str(exc)[:200]}"

    return func.HttpResponse(
        json.dumps(valida_out, ensure_ascii=False, default=str),
        status_code=200,
        mimetype="application/json",
    )
