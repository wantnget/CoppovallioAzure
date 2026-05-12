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
EDAD_MINIMA = 18
FORMATO_FECHA_API = "%m/%d/%Y"

VALIDO = 1
NO_VALIDO = 2


def generar_radicado(cedula: str) -> str:
    return f"{cedula}_{datetime.now().strftime('%d%m%y%H%M%S')}"


def parsear_fecha(fecha_str: str) -> datetime | None:
    """Parsea una fecha en el formato que entrega la API (M/D/YYYY)."""
    if not fecha_str:
        return None
    try:
        return datetime.strptime(str(fecha_str), FORMATO_FECHA_API)
    except (ValueError, TypeError):
        return None


def calcular_edad(fecha_nac: datetime, hoy: datetime) -> int:
    edad = hoy.year - fecha_nac.year
    if (hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day):
        edad -= 1
    return edad


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


def extraer_asociado(data_api: dict | None) -> dict | None:
    """Devuelve el primer asociado del response, o None si no existe."""
    if not isinstance(data_api, dict):
        return None
    lista = data_api.get("asociadoList")
    if not isinstance(lista, list) or not lista:
        return None
    asociado = lista[0]
    return asociado if isinstance(asociado, dict) else None


def validar_asociado(asociado: dict | None) -> int:
    """El campo 'asociado' debe ser igual a 1."""
    if not asociado:
        return NO_VALIDO
    return VALIDO if asociado.get("asociado") == 1 else NO_VALIDO


def validar_activo(asociado: dict | None) -> int:
    """El campo 'activo' debe ser igual a 1."""
    if not asociado:
        return NO_VALIDO
    return VALIDO if asociado.get("activo") == 1 else NO_VALIDO


def validar_edad(asociado: dict | None) -> int:
    """El asociado debe ser mayor de 18 años."""
    if not asociado:
        return NO_VALIDO
    fecha_nac = parsear_fecha(asociado.get("fechaNacimiento"))
    if not fecha_nac:
        return NO_VALIDO
    edad = calcular_edad(fecha_nac, datetime.now())
    return VALIDO if edad >= EDAD_MINIMA else NO_VALIDO


def validar_no_retirado(asociado: dict | None) -> int:
    """El asociado no debe tener una fecha de retiro vigente."""
    if not asociado:
        return NO_VALIDO
    fecha_retiro_str = asociado.get("fechaRetiro")
    if not fecha_retiro_str:
        return VALIDO
    fecha_retiro = parsear_fecha(fecha_retiro_str)
    if not fecha_retiro:
        return VALIDO
    return NO_VALIDO if fecha_retiro <= datetime.now() else VALIDO


def procesar_solicitud(payload: dict) -> dict:
    cedula = payload.get("id")

    if not cedula:
        return {
            "radicado": None,
            "result": {
                "valida_asociado": NO_VALIDO,
                "valida_activo": NO_VALIDO,
                "valida_edad": NO_VALIDO,
                "valida_no_retirado": NO_VALIDO,
                "valida1": NO_VALIDO,
                "mensaje": "Campo 'id' requerido",
            },
            "datos_asociado": None,
        }

    radicado = generar_radicado(str(cedula))
    data_api = consultar_coopvalili(str(cedula))
    asociado = extraer_asociado(data_api)

    if asociado:
        valida_asociado = validar_asociado(asociado)
        valida_activo = validar_activo(asociado)
        valida_edad = validar_edad(asociado)
        valida_no_retirado = validar_no_retirado(asociado)
    else:
        valida_asociado = NO_VALIDO
        valida_activo = NO_VALIDO
        valida_edad = NO_VALIDO
        valida_no_retirado = NO_VALIDO

    todas = [valida_asociado, valida_activo, valida_edad, valida_no_retirado]
    if all(v == VALIDO for v in todas):
        valida1 = VALIDO
        mensaje = "Validaciones exitosas"
    else:
        valida1 = NO_VALIDO
        razones = []
        if not asociado:
            razones.append("usuario sin datos en Coopvalili")
        else:
            if valida_asociado == NO_VALIDO:
                razones.append("usuario no es asociado")
            if valida_activo == NO_VALIDO:
                razones.append("usuario inactivo")
            if valida_edad == NO_VALIDO:
                razones.append("usuario menor de 18 años")
            if valida_no_retirado == NO_VALIDO:
                razones.append("usuario retirado")
        mensaje = "; ".join(razones)

    return {
        "radicado": radicado,
        "result": {
            "valida_asociado": valida_asociado,
            "valida_activo": valida_activo,
            "valida_edad": valida_edad,
            "valida_no_retirado": valida_no_retirado,
            "valida1": valida1,
            "mensaje": mensaje,
        },
        "datos_asociado": asociado,
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    log.info("request recibido", extra={"endpoint": "/api/valida1"})

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
        return func.HttpResponse(
            json.dumps({"error": "Body JSON inválido"}),
            status_code=400,
            mimetype="application/json",
        )

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
