import os
import json
import urllib.request
import urllib.error
import traceback
from azure.storage.blob import BlobServiceClient, ContentSettings

def _get_blob_client(cedula: str, filename: str):
    conn = os.environ["COPRODIGITAL_BLOB_CONN"]
    container = os.environ.get("COPRODIGITAL_BLOB_CONTAINER", "motor-data")
    bsc = BlobServiceClient.from_connection_string(conn)
    cc = bsc.get_container_client(container)
    blob_name = f"{cedula}/{filename}"
    return cc.get_blob_client(blob_name)


def save_json_blob_by_id(cedula: str, filename: str, data: dict):
    print(f"[blob_loader] Guardando {cedula}/{filename} en Azure Blob")
    blob_client = _get_blob_client(cedula, filename)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    blob_client.upload_blob(
        payload,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json")
    )
    print(f"[blob_loader] OK — {cedula}/{filename}")


def load_json_blob_by_id(cedula: str, filename: str) -> dict:
    blob_client = _get_blob_client(cedula, filename)
    data = blob_client.download_blob().readall().decode("utf-8")
    return json.loads(data)

def _guardar_en_supabase(cedula: str, data: dict):
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_KEY", "")

    if not supabase_url or not supabase_key:
        print("[Supabase] URL o KEY no configuradas — saltando")
        return

    resumen = data.get("resumen_final", {}) or {}
    motor   = data.get("motor_want", {}) or {}

    payload = {
        "cedula":        cedula,
        "req_amount":    motor.get("monto_credito"),
        "request_json":  data.get("datos_asociado", {}),
        "response_json": data,
        "decision":      str(motor.get("motor_2", "")),
        "score_exp":     resumen.get("score_expe"),
        "score_tu":      resumen.get("score_trans"),
        "ingreso_total": resumen.get("ingreso_total"),
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url  = f"{supabase_url}/rest/v1/motor_requests"

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type",  "application/json")
    req.add_header("apikey",        supabase_key)
    req.add_header("Authorization", f"Bearer {supabase_key}")
    req.add_header("Prefer",        "return=minimal")

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[Supabase] Guardado cédula {cedula} — status {resp.status}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"[Supabase] HTTP Error {e.code}: {error_body}")
        raise
