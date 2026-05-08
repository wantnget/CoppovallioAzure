import json
import os
from datetime import datetime

import requests
import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger
from shared.blob_loader import save_json_blob_by_id
from shared.supabase_saver import save_valida1_supabase

log = get_logger("valida1")

TIMEOUT = 15
EDAD_MINIMA = 18
ANTIGUEDAD_MINIMA_MESES = 1
FORMATO_FECHA_API = "%m/%d/%Y"

VALIDO = 1
NO_VALIDO = 2


def generar_radicado(cedula: str) -> str:
    return f"{cedula}_{datetime.now().strftime('%d%m%y%H%M%S')}"


def parsear_fecha(fecha_str: str) -> datetime | None:
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


def calcular_meses(fecha_ini: datetime, hoy: datetime) -> int:
    meses = (hoy.year - fecha_ini.year) * 12 + (hoy.month - fecha_ini.month)
    if hoy.day < fecha_ini.day:
        meses -= 1
    return meses


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
    if not isinstance(data_api, dict):
        return None
    lista = data_api.get("asociadoList")
    if not isinstance(lista, list) or not lista:
        return None
    asociado = lista[0]
    return asociado if isinstance(asociado, dict) else None


def validar_id_api(asociado: dict | None) -> int:
    if not asociado:
        return NO_VALIDO
    nombre = str(asociado.get("nombre", "")).strip()
    apellido = str(asociado.get("primer_apellido", "")).strip()
    return VALIDO if (nombre and apellido) else NO_VALIDO


def validar_edad(asociado: dict | None) -> int:
    if not asociado:
        return NO_VALIDO
    fecha_nac = parsear_fecha(asociado.get("fechaNacimiento"))
    if not fecha_nac:
        return NO_VALIDO
    edad = calcular_edad(fecha_nac, datetime.now())
    return VALIDO if edad >= EDAD_MINIMA else NO_VALIDO


def validar_antiguedad(asociado: dict | None) -> int:
    if not asociado:
        return NO_VALIDO
    fecha_ing = parsear_fecha(asociado.get("fecha_ingreso"))
    if not fecha_ing:
        return NO_VALIDO
    meses = calcular_meses(fecha_ing, datetime.now())
    return VALIDO if meses >= ANTIGUEDAD_MINIMA_MESES else NO_VALIDO


def validar_no_retirado(asociado: dict | None) -> int:
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
                "valida_id": NO_VALIDO,
                "valida_edad": NO_VALIDO,
                "valida_antiguedad": NO_VALIDO,
                "valida_no_retirado": NO_VALIDO,
                "valida1": NO_VALIDO,
                "mensaje": "Campo 'id' requerido",
            },
            "datos_asociado": None,
        }

    radicado = generar_radicado(str(cedula))
    data_api = consultar_coopvalili(str(cedula))
    asociado = extraer_asociado(data_api)

    valida_id = validar_id_api(asociado)

    if valida_id == VALIDO:
        valida_edad = validar_edad(asociado)
        valida_antiguedad = validar_antiguedad(asociado)
        valida_no_retirado = validar_no_retirado(asociado)
    else:
        valida_edad = NO_VALIDO
        valida_antiguedad = NO_VALIDO
        valida_no_retirado = NO_VALIDO

    todas = [valida_id, valida_edad, valida_antiguedad, valida_no_retirado]
    if all(v == VALIDO for v in todas):
        valida1 = VALIDO
        mensaje = "Validaciones exitosas"
    else:
        valida1 = NO_VALIDO
        razones = []
        if valida_id == NO_VALIDO:
            razones.append("usuario sin datos en Coopvalili")
        else:
            if valida_edad == NO_VALIDO:
                razones.append("usuario menor de 18 años")
            if valida_antiguedad == NO_VALIDO:
                razones.append("antigüedad menor a 1 mes")
            if valida_no_retirado == NO_VALIDO:
                razones.append("usuario retirado")
        mensaje = "; ".join(razones)

    return {
        "radicado": radicado,
        "result": {
            "valida_id": valida_id,
            "valida_edad": valida_edad,
            "valida_antiguedad": valida_antiguedad,
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
    radicado = valida_out.get("radicado") or ""

    try:
        save_valida1_supabase(radicado, cedula, valida_out)
        valida_out["_supabase_save"] = "OK"
    except Exception as exc:
        log.warning("fallo supabase valida1", extra={"cedula": cedula, "error": str(exc)})
        valida_out["_supabase_save"] = f"ERROR: {str(exc)[:200]}"

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
