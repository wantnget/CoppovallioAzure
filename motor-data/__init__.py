import json
import os
from datetime import datetime
from typing import Any

import requests
from requests.auth import HTTPBasicAuth
import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger
from shared.blob_loader import save_json_blob_by_id, load_json_blob_by_id
from shared.supabase_saver import save_motor_data_supabase

log = get_logger("motor_data")

TIMEOUT = 30
FORMATO_FECHA_API = "%m/%d/%Y"

API_OK = "ok"
API_FAIL = "fail"
API_NO_DATA = "no_data"

PARAM_GARANTIA = "Aportes"
PARAM_TASA_USURA = 0.3498
PARAM_PLAZO_TARJETAS = 36
PARAM_PLAZO_CONSULTA_TU = 18
PARAM_MOTIVO_CONSULTA_TU = "24"
PARAM_TIPO_IDENTIFICACION_TU = "1"

UMBRAL_INSTANCIA_GERENTE = 4_000_000
INSTANCIA_GERENTE = "Gerente"
INSTANCIA_COMITE = "comite de credito"

PARAMETRO_CREDITO_POR_LINEA = {
    "Eventos": 1_000_000,
    "Cred.Ord, Gerencia": 2_000_000,
    "Cred.Ord. Ant.": 1_500_000,
    "Diez Años": 5_000_000,
    "Polizas": 800_000,
    "Soat": 500_000,
    "Turismo": 1_500_000,
}

CATEGORIAS_DEUDA_SECTOR = [
    "sfConsumo", "noRotativoMdo", "sfComercial", "vivienda",
    "sfMicrocredito", "sectorSolidario", "srcomercio", "srservicios",
]

# Columnas que se piden a la API de datos-asociado.
# Pedimos solo lo que necesita motor_data; puede crecer si se requieren más campos.
COLUMNAS_DATOS_ASOCIADO = "tipo_vivienda"


def parsear_fecha(fecha_str: str) -> datetime | None:
    """Parsea una fecha en formato M/D/YYYY (Coopvalili) o D/M/YYYY (TU)."""
    if not fecha_str:
        return None
    for fmt in (FORMATO_FECHA_API, "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(fecha_str), fmt)
        except (ValueError, TypeError):
            continue
    return None


def to_float(valor: Any) -> float:
    if valor is None:
        return 0.0
    try:
        return float(str(valor).replace(",", "").replace("$", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def to_int(valor: Any) -> int:
    try:
        return int(to_float(valor))
    except (ValueError, TypeError):
        return 0


def calcular_edad(fecha_nac_str: str) -> int:
    fecha = parsear_fecha(fecha_nac_str)
    if not fecha:
        return 0
    hoy = datetime.now()
    edad = hoy.year - fecha.year
    if (hoy.month, hoy.day) < (fecha.month, fecha.day):
        edad -= 1
    return edad


def calcular_antiguedad_anios(fecha_str: str) -> float:
    fecha = parsear_fecha(fecha_str)
    if not fecha:
        return 0.0
    hoy = datetime.now()
    return round((hoy - fecha).days / 365.25, 2)


def tasa_usura_periodica(tasa_anual: float) -> float:
    """Convierte tasa anual efectiva a periódica mensual: (1+i)^(1/12) - 1."""
    return round((1 + tasa_anual) ** (1 / 12) - 1, 4)


def calcular_instancia_aprobacion(monto: Any) -> str:
    """
    Define la instancia de aprobación según el monto solicitado:
      - 0 a 4.000.000  -> Gerente
      - > 4.000.000    -> comite de credito
    """
    monto_num = to_float(monto)
    if monto_num <= UMBRAL_INSTANCIA_GERENTE:
        return INSTANCIA_GERENTE
    return INSTANCIA_COMITE


def cargar_radicado_valida1(cedula: str) -> str | None:
    """Carga el radicado generado por valida1 desde el blob, o None si no existe."""
    try:
        valida_blob = load_json_blob_by_id(cedula, "valida_output.json")
        return valida_blob.get("radicado")
    except Exception:
        return None


def consultar_coopvalili(cedula: str) -> tuple[dict | None, str]:
    base_url = os.environ.get("COOPVALILI_URL", "")
    token = os.environ.get("COOPVALILI_TOKEN", "")
    url = f"{base_url}/{cedula}"
    headers = {"X-Auth-Token": token}

    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=True)
        log.info("consulta coopvalili", extra={
                 "cedula": cedula, "status": resp.status_code})
        resp.raise_for_status()
        return resp.json(), API_OK
    except requests.exceptions.RequestException as e:
        log.error("fallo coopvalili", extra={
                  "cedula": cedula, "error": str(e)})
        return None, API_FAIL
    except ValueError as e:
        log.error("respuesta coopvalili no es JSON",
                  extra={"cedula": cedula, "error": str(e)})
        return None, API_FAIL


def consultar_transunion(cedula: str, primer_apellido: str,
                         salario: int) -> tuple[dict | None, str]:
    url = os.environ.get("TRANSUNION_URL", "")
    user = os.environ.get("TRANSUNION_USER", "")
    password = os.environ.get("TRANSUNION_PASSWORD", "")

    body = {
        "tipoIdentificacion": PARAM_TIPO_IDENTIFICACION_TU,
        "numeroIdentificacion": str(cedula),
        "motivoConsulta": PARAM_MOTIVO_CONSULTA_TU,
        "salario": str(salario),
        "primerApellido": primer_apellido,
        "usura": f"{PARAM_TASA_USURA * 100 / 12:.2f}",  
        "plazos": str(PARAM_PLAZO_CONSULTA_TU),
    }

    try:
        resp = requests.post(url, json=body, auth=HTTPBasicAuth(user, password),
                             timeout=TIMEOUT)
        log.info("consulta transunion", extra={
                 "cedula": cedula, "status": resp.status_code})
        resp.raise_for_status()
        return resp.json(), API_OK
    except requests.exceptions.RequestException as e:
        log.error("fallo transunion", extra={
                  "cedula": cedula, "error": str(e)})
        return None, API_FAIL
    except ValueError as e:
        log.error("respuesta transunion no es JSON",
                  extra={"cedula": cedula, "error": str(e)})
        return None, API_FAIL


def consultar_datos_asociado(cedula: str) -> tuple[dict | None, str]:
    """
    Consulta la API datos-asociado (Coppovallio) para campos extra como tipo_vivienda.
    Devuelve (data, status).
    """
    url = os.environ.get("DATOS_ASOCIADO_URL", "")
    headers = {"x-api-key": "332eecd22c97ffbfa25b1d28f408d5eb49186944064ff557441f26f18779cfcb"}
    body = {
        "cedula": str(cedula),
        "columna": COLUMNAS_DATOS_ASOCIADO,
    }
    try:
        resp = requests.post(url, json=body, headers=headers,
                             timeout=TIMEOUT, verify=True)
        log.info("consulta datos_asociado", extra={
                 "cedula": cedula, "status": resp.status_code})
        resp.raise_for_status()
        return resp.json(), API_OK
    except requests.exceptions.RequestException as e:
        log.error("fallo datos_asociado", extra={
                  "cedula": cedula, "error": str(e)})
        return None, API_FAIL
    except ValueError as e:
        log.error("respuesta datos_asociado no es JSON",
                  extra={"cedula": cedula, "error": str(e)})
        return None, API_FAIL


def extraer_tipo_vivienda(data: dict | None, fallback: Any = 0) -> Any:
    """
    Extrae 'tipo_vivienda' de la respuesta de datos-asociado.
    Si el campo no existe o la data es invalida, devuelve el fallback.
    """
    if not isinstance(data, dict):
        return fallback
    datos = data.get("datos") or {}
    tv = datos.get("tipo_vivienda")
    return tv if tv is not None else fallback


def _coopvalili_vacio() -> dict[str, Any]:
    return {
        "asociado": {},
        "primer_apellido": "",
        "segundo_apellido": "",
        "nombre": "",
        "empresa": "",
        "aportes": 0,
        "aporteMensual": 0,
        "ahorrosFondo": 0,
        "aportesAhorros": 0,
        "deudaCoopvalili": 0,
        "cuotarecogeCoopvalili": 0,
        "fechaIngreso": "",
        "fechaNacimiento": "",
        "tipoVivienda": 0,
    }


def extraer_datos_coopvalili(data: dict | None) -> dict[str, Any]:
    """Extrae los campos relevantes del response de Coopvalili."""
    if not isinstance(data, dict):
        return _coopvalili_vacio()

    asociado_list = data.get("asociadoList") or []
    aporte_list = data.get("aporteList") or []
    cartera_list = data.get("carteraList") or []

    asociado = asociado_list[0] if asociado_list else {}
    aporte = aporte_list[0] if aporte_list else {}

    deuda_coop = sum(c.get("saldoCapital", 0) for c in cartera_list)
    cuota_coop = sum(c.get("valorCuotaFija", 0) for c in cartera_list)

    aportes = aporte.get("saldo_fecha", 0)
    aporte_mensual = aporte.get("valor_aporte_mensual", 0)
    ahorros_fondo = 0  

    return {
        "asociado": asociado,
        "primer_apellido": asociado.get("primer_apellido", ""),
        "segundo_apellido": asociado.get("segundo_apellido", ""),
        "nombre": asociado.get("nombre", ""),
        "empresa": asociado.get("cliente_empresa", ""),
        "aportes": aportes,
        "aporteMensual": aporte_mensual,
        "ahorrosFondo": ahorros_fondo,
        "aportesAhorros": aportes + ahorros_fondo,
        "deudaCoopvalili": deuda_coop,
        "cuotarecogeCoopvalili": cuota_coop,
        "fechaIngreso": asociado.get("fecha_ingreso", ""),
        "fechaNacimiento": asociado.get("fechaNacimiento", ""),
        "tipoVivienda": asociado.get("estrato", 0),
    }


def _transunion_vacio() -> dict[str, Any]:
    return {
        "deudaSector": 0.0,
        "deudaTcsector": 0.0,
        "cuposTdc": 0.0,
        "cuotarecogeSector": 0.0,
        "egresosSector": 0.0,
        "scoreCifin": 0,
    }


def extraer_datos_transunion(data: dict | None) -> dict[str, Any]:
    """
    Extrae deudas, cupos, cuotas y score desde TransUnion.
    detalleObligacionCartera trae listas con [cantidad, valorInicial, saldo, cuota].
    """
    if not isinstance(data, dict):
        return _transunion_vacio()

    resultado = data.get("resultado", {}) or {}
    detalle = resultado.get("detalleObligacionCartera", {}) or {}

    deuda_sector = sum(
        to_float(detalle.get(c, ["0", "", "", ""])[2])
        for c in CATEGORIAS_DEUDA_SECTOR
    )
    cuota_sector = sum(
        to_float(detalle.get(c, ["0", "", "", ""])[3])
        for c in CATEGORIAS_DEUDA_SECTOR
    )

    tc = detalle.get("tarjetaDeCredito", ["0", "", "", ""])
    deuda_tc = to_float(tc[2])
    cupos_tdc = to_float(tc[1])
    cuota_tdc = to_float(tc[3])

    score = to_int(resultado.get("scoreIngresoCapEnd", {}).get("score"))

    return {
        "deudaSector": deuda_sector,
        "deudaTcsector": deuda_tc,
        "cuposTdc": cupos_tdc,
        "cuotarecogeSector": cuota_sector + cuota_tdc,
        "egresosSector": cuota_sector + cuota_tdc,
        "scoreCifin": score,
    }


def armar_detallado_want(payload: dict, coop: dict, tu: dict,
                         radicado: str | None,
                         tipo_vivienda: Any = 0) -> dict[str, Any]:
    """Construye el dict con las variables del motor en el orden de la columna B."""
    cedula = payload.get("id", "")
    linea = payload.get("lineaCredito", "")
    monto = payload.get("monto", 0)
    asociado = coop.get("asociado", {}) or {}

    edad = calcular_edad(coop.get("fechaNacimiento", ""))
    antiguedad_fondo = calcular_antiguedad_anios(coop.get("fechaIngreso", ""))
    antiguedad_laboral = calcular_antiguedad_anios(
        asociado.get("fecha_ingreso_empresa", ""))
    tasa_usura_per = tasa_usura_periodica(PARAM_TASA_USURA)

    parametro_credito = PARAMETRO_CREDITO_POR_LINEA.get(linea, 0)
    instancia_aprobacion = calcular_instancia_aprobacion(monto)
    credito_afianzado = to_int(1)

    cedula_str = str(cedula)
    id_out = int(cedula_str) if cedula_str.isdigit() else cedula_str

    return {
        "radicado":              radicado,                        # Heredado de valida1
        "garantia":              PARAM_GARANTIA,                  # Parametro
        "id":                    id_out,                          # Chat
        "primer_apellido":       coop["primer_apellido"],         # Solido
        "segundo_apellido":      coop["segundo_apellido"],        # Solido
        "nombre":                coop["nombre"],                  # Solido
        "empresa":               coop["empresa"],                 # Solido
        "aportes":               coop["aportes"],                 # Solido
        "aporteMensual":         coop["aporteMensual"],           # Solido
        "deudaCoopvalili":       coop["deudaCoopvalili"],         # Solido
        "deudaSector":           tu["deudaSector"],               # Transunion
        "deudaTcsector":         tu["deudaTcsector"],             # Transunion
        "cuposTdc":              tu["cuposTdc"],                  # Transunion
        "cuotarecogeCoopvalili": coop["cuotarecogeCoopvalili"],   # Solido
        "cuotarecogeSector":     tu["cuotarecogeSector"],         # Transunion
        "salario":               payload.get("salario", 0),       # Chat
        "tipoSalario":           payload.get("tipoSalario", ""),  # Chat
        "egresosVolante":        payload.get("egresosVolante", 0),  # Chat
        "egresosSector":         tu["egresosSector"],             # Transunion
        "scoreCifin":            tu["scoreCifin"],                # Transunion
        "frecuenciaPagos":       payload.get("frecuenciaPagos", ""),  # Chat
        "aportesAhorros":        coop["aportesAhorros"],          # Solido
        "lineaCredito":          linea,                           # Chat
        "montoSolicitado":       monto,                           # Chat
        "parametroCredito":      parametro_credito,               # Parametro
        "instanciaAprobacion":   instancia_aprobacion,            # Parametro (segun monto)
        "creditoAfianzado":      credito_afianzado,               #  (Si=1, No=2)
        "ahorrosFondo":          coop["ahorrosFondo"],            # Solido
        "fechaIngreso":          coop["fechaIngreso"],            # Solido
        "fechaNacimiento":       coop["fechaNacimiento"],         # Solido
        "edad":                  edad,                            # Calculo Motor
        "personasCargo":         payload.get("personasCargo", 0),  # Chat
        # Base Asociados
        "tipoVivienda":          tipo_vivienda,
        "antiguedadFondo":       antiguedad_fondo,                # Calculo Motor
        "antiguedadLaboral":     antiguedad_laboral,              # Base Asociados
        "tasaUsura":             PARAM_TASA_USURA,                # Parametro
        "tasausuraper":          tasa_usura_per,                  # Calculo Motor
        "plazoTarjetas":         PARAM_PLAZO_TARJETAS,            # Parametro
    }


def procesar_solicitud(payload: dict, radicado: str | None) -> dict[str, Any]:
    cedula = payload.get("id")

    if not cedula:
        return {
            "status": "error",
            "detallado_want": None,
            "meta": {
                "coopvalili": API_NO_DATA,
                "transunion": API_NO_DATA,
                "datos_asociado": API_NO_DATA,
                "mensaje": "Campo 'id' requerido",
            },
            "apis": {
                "coopvalili": None,
                "transunion": None,
                "datos_asociado": None,
            },
        }

    cedula_str = str(cedula)

    coop_raw, coop_status = consultar_coopvalili(cedula_str)
    coop = extraer_datos_coopvalili(coop_raw)

    if coop_status == API_OK and not coop["asociado"]:
        coop_status = API_NO_DATA

    salario = to_int(payload.get("salario"))
    tu_raw, tu_status = consultar_transunion(
        cedula_str, coop["primer_apellido"], salario
    )
    tu = extraer_datos_transunion(tu_raw)

    if tu_status == API_OK and not (tu_raw or {}).get("resultado"):
        tu_status = API_NO_DATA

    # Datos-Asociado: trae tipo_vivienda (y otras columnas si se piden)
    asociado_raw, asociado_status = consultar_datos_asociado(cedula_str)
    tipo_vivienda = extraer_tipo_vivienda(
        asociado_raw,
        fallback=coop.get("tipoVivienda", 0),
    )
    # Si la API respondió OK pero no trajo el campo, marcar como no_data
    if asociado_status == API_OK and (
        not isinstance(asociado_raw, dict)
        or not (asociado_raw.get("datos") or {}).get("tipo_vivienda")
    ):
        asociado_status = API_NO_DATA

    detallado = armar_detallado_want(payload, coop, tu, radicado, tipo_vivienda)

    razones = []
    if coop_status == API_FAIL:
        razones.append("API Coopvalili falló")
    elif coop_status == API_NO_DATA:
        razones.append("Coopvalili no trajo datos del asociado")
    if tu_status == API_FAIL:
        razones.append("API TransUnion falló")
    elif tu_status == API_NO_DATA:
        razones.append("TransUnion no trajo datos")
    if asociado_status == API_FAIL:
        razones.append("API datos-asociado falló")
    elif asociado_status == API_NO_DATA:
        razones.append("datos-asociado no trajo tipo_vivienda")

    if not razones:
        status = "ok"
        mensaje = "Todas las APIs respondieron correctamente"
    elif coop_status == API_OK or tu_status == API_OK:
        status = "partial"
        mensaje = "; ".join(razones)
    else:
        status = "error"
        mensaje = "; ".join(razones)

    return {
        "status": status,
        "detallado_want": detallado,
        "meta": {
            "coopvalili": coop_status,
            "transunion": tu_status,
            "datos_asociado": asociado_status,
            "mensaje": mensaje,
        },
        "apis": {
            "coopvalili": coop_raw,
            "transunion": tu_raw,
            "datos_asociado": asociado_raw,
        },
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    log.info("request recibido", extra={"endpoint": "/api/motor_data"})

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

    cedula = str(payload.get("id", "sin_cedula"))

    radicado_valida1 = cargar_radicado_valida1(cedula)

    try:
        salida = procesar_solicitud(payload, radicado_valida1)
    except Exception as exc:
        log.error("error en procesar_solicitud", extra={"error": str(exc)})
        return func.HttpResponse(
            json.dumps({"error": "Error interno del servidor"}),
            status_code=500,
            mimetype="application/json",
        )

    try:
        save_motor_data_supabase(radicado_valida1, cedula, salida)
        salida["_supabase_save"] = "OK"
    except Exception as exc:
        log.warning("fallo supabase motor_data",
                    extra={"cedula": cedula, "error": str(exc)})
        salida["_supabase_save"] = f"ERROR: {str(exc)[:200]}"

    try:
        save_json_blob_by_id(cedula, "motor_data_output.json", salida)
        salida["_blob_save"] = "OK"
        log.info("blob guardado", extra={"cedula": cedula})
    except Exception as exc:
        log.warning("fallo blob", extra={"cedula": cedula, "error": str(exc)})
        salida["_blob_save"] = f"ERROR: {str(exc)[:200]}"

    respuesta = {k: v for k, v in salida.items() if k != "apis"}

    return func.HttpResponse(
        json.dumps(respuesta, ensure_ascii=False, default=str),
        status_code=200,
        mimetype="application/json",
    )
