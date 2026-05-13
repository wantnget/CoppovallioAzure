import json
import os
import urllib.request
import urllib.error

import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger

log = get_logger("datos-asociado")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TABLE_NAME   = "datos_asociado"

COLUMNAS_VALIDAS = {
    "cedula", "primer_apellido", "nombre", "ciudad",
    "estado_civil", "estado_civil_norm", "edad", "personas_cargo",
    "cliente_empresa", "fecha_ingreso", "fecha_ingreso_empresa",
    "antiguedad_coop", "antiguedad_laboral",
    "salario", "aportes", "deuda_coopvalili", "usuario_credito",
    "tipo_vivienda", "nivel", "cuota_disponible", "nombre_asociado",
}


def fetch_asociado(cedula: str, columnas: list[str]) -> dict | None:
    select = ",".join(columnas)
    url    = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?cedula=eq.{cedula}&select={select}&limit=1"
    req    = urllib.request.Request(
        url,
        method="GET",
        headers={
            "apikey":        SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            rows = json.loads(resp.read().decode())
            return rows[0] if rows else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase HTTP {e.code}: {e.read().decode()}") from e


def _resp(body: dict, status: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False, default=str),
        status_code=status,
        mimetype="application/json",
    )


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        validar_api_key(req.headers.get("x-api-key"))
    except AuthError as exc:
        return _resp({"error": str(exc), "code": exc.code}, 401)

    try:
        payload = req.get_json()
    except ValueError:
        return _resp({"error": "Body JSON invalido"}, 400)

    cedula  = str(payload.get("cedula", "")).strip()
    columna = payload.get("columna")

    if not cedula:
        return _resp({"error": "Campo 'cedula' requerido"}, 400)

    if columna:
        if isinstance(columna, str):
            cols_solicitadas = [c.strip() for c in columna.split(",") if c.strip()]
        elif isinstance(columna, list):
            cols_solicitadas = [str(c).strip() for c in columna if str(c).strip()]
        else:
            return _resp({"error": "'columna' debe ser string o lista"}, 400)

        invalidas = [c for c in cols_solicitadas if c not in COLUMNAS_VALIDAS]
        if invalidas:
            return _resp({
                "error":  f"Columnas invalidas: {invalidas}",
                "validas": sorted(COLUMNAS_VALIDAS),
            }, 400)
        columnas = cols_solicitadas
    else:
        columnas = list(COLUMNAS_VALIDAS)

    log.info("consulta datos-asociado", extra={"cedula": cedula, "columnas": columnas})

    try:
        row = fetch_asociado(cedula, columnas)
    except RuntimeError as exc:
        log.error("error Supabase", extra={"cedula": cedula, "error": str(exc)})
        return _resp({"error": "Error consultando Supabase"}, 500)

    if row is None:
        return _resp({"error": f"Cedula '{cedula}' no encontrada"}, 404)

    return _resp({"cedula": cedula, "datos": row}, 200)
