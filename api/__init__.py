import azure.functions as func
import json
import os
import time
import traceback
from .motor import run_motor
from .blob_loader import save_json_blob_by_id


async def main(req: func.HttpRequest) -> func.HttpResponse:
    print("=== [0] COPRODIGITAL MOTOR INICIANDO ===", flush=True)

    # ── Autenticación por x-api-key ───────────────────────────────
    api_key_recibida = req.headers.get("x-api-key", "") or req.headers.get("X-Api-Key", "")
    api_key_esperada = os.environ.get("API_KEY", "")

    if api_key_esperada and api_key_recibida != api_key_esperada:
        print("[1] ERROR: API key inválida — abortando", flush=True)
        return func.HttpResponse(
            json.dumps({"error": "No autorizado"}),
            status_code=401,
            mimetype="application/json"
        )

    print("[1] Autenticación OK", flush=True)

    # ── Parsear body ──────────────────────────────────────────────
    try:
        payload = req.get_json()
    except Exception:
        return func.HttpResponse(
            json.dumps({"error": "Body JSON inválido"}),
            status_code=400,
            mimetype="application/json"
        )

    cedula = str(payload.get("id", ""))
    print(f"[2] Cédula recibida: '{cedula}'", flush=True)
    print(f"[2] Campos recibidos: {list(payload.keys())}", flush=True)

    # ── Variables de entorno (diagnóstico) ────────────────────────
    print(f"[3] PROXY_HOST: {os.environ.get('PROXY_HOST', 'NO CONFIGURADO')}", flush=True)
    print(f"[3] PROXY_PORT: {os.environ.get('PROXY_PORT', 'NO CONFIGURADO')}", flush=True)
    print(f"[3] BLOB_CONN configurada: {bool(os.environ.get('COPRODIGITAL_BLOB_CONN'))}", flush=True)
    print(f"[3] SUPABASE_URL configurada: {bool(os.environ.get('SUPABASE_URL'))}", flush=True)

    # ── Ejecución del motor ───────────────────────────────────────
    t0 = time.time()
    try:
        result = run_motor(payload)
        t1 = time.time()
        print(f"[4] run_motor OK — {t1 - t0:.1f}s", flush=True)
    except Exception as e:
        t1 = time.time()
        print(f"[4] ERROR en run_motor — {t1 - t0:.1f}s", flush=True)
        print(f"[4] Traceback:\n{traceback.format_exc()}", flush=True)
        return func.HttpResponse(
            json.dumps({
                "error": str(e),
                "tipo": type(e).__name__,
                "detalle": traceback.format_exc()
            }),
            status_code=500,
            mimetype="application/json"
        )

    result["_tiempo_motor"] = f"{t1 - t0:.1f}s"

    # ── Guardar en Azure Blob ─────────────────────────────────────
    print("[5] Guardando en Azure Blob Storage...", flush=True)
    try:
        save_json_blob_by_id(cedula, "motor_output.json", result)
        result["_blob_save"] = "OK"
        print("[5] Blob OK", flush=True)
    except Exception as e:
        print(f"[5] ERROR Blob: {type(e).__name__}: {e}", flush=True)
        result["_blob_save"] = f"ERROR: {str(e)[:300]}"

    # ── Guardar en Supabase ───────────────────────────────────────
    print("[6] Guardando en Supabase...", flush=True)
    try:
        from .blob_loader import _guardar_en_supabase
        _guardar_en_supabase(cedula, result)
        result["_supabase_save"] = "OK"
        print("[6] Supabase OK", flush=True)
    except Exception as e:
        print(f"[6] ERROR Supabase: {type(e).__name__}: {e}", flush=True)
        result["_supabase_save"] = f"ERROR: {str(e)[:300]}"

    print("[7] Respondiendo OK", flush=True)
    return func.HttpResponse(
        json.dumps(result, ensure_ascii=False),
        status_code=200,
        mimetype="application/json"
    )
