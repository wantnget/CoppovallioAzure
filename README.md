# coppovallio-api

Azure Function App en Python 3.11 (modelo v1) que expone endpoints HTTP con autenticación por `x-api-key`.

## Estructura

```
coppovallioAzure/
├── shared/              # Código reutilizable por todas las funciones
│   ├── auth.py          # validate_api_key con hmac.compare_digest
│   ├── logger.py        # get_logger — logs estructurados para App Insights
│   └── exceptions.py    # MotorError, AuthError, ValidationError
├── ping/                # GET /api/ping — health check
├── api/                 # POST /api/motor/run — motor de decisión
├── host.json
├── requirements.txt
└── local.settings.json  # (excluido de git)
```

## Variables de entorno

| Variable | Descripción | Obligatoria |
|---|---|---|
| `API_KEY` | Clave que deben enviar los clientes en `x-api-key` | Sí |
| `LOG_LEVEL` | Nivel de logging (`DEBUG`, `INFO`, `WARNING`) | No (default `INFO`) |
| `COPRODIGITAL_BLOB_CONN` | Connection string de Azure Blob Storage | Sí (motor) |
| `SUPABASE_URL` | URL del proyecto Supabase | Sí (motor) |
| `SUPABASE_KEY` | API key de Supabase (service role) | Sí (motor) |
| `PROXY_HOST` / `PROXY_PORT` | Proxy saliente si aplica | No |

Configúralas en Azure Portal → Function App → **Settings → Environment variables**, o en `local.settings.json` para desarrollo local.

## Correr localmente

```bash
# Prerrequisitos: Azure Functions Core Tools v4, Python 3.11
pip install -r requirements.txt
func start
```

Prueba el ping:

```bash
curl http://localhost:7071/api/ping -H "x-api-key: dev-key-local"
# {"status": "ok", "timestamp": "2026-..."}
```

## Agregar una nueva función (paso a paso)

1. **Crea el directorio** con el nombre del endpoint:

   ```
   mi_endpoint/
   ├── __init__.py
   └── function.json
   ```

2. **`function.json`** — define el trigger y la ruta:

   ```json
   {
     "scriptFile": "__init__.py",
     "bindings": [
       {
         "type": "httpTrigger",
         "authLevel": "anonymous",
         "direction": "in",
         "name": "req",
         "methods": ["POST"],
         "route": "mi_endpoint"
       },
       { "type": "http", "direction": "out", "name": "$return" }
     ]
   }
   ```

3. **`__init__.py`** — importa `shared` y maneja el request:

   ```python
   import json
   import azure.functions as func
   from ..shared import validate_api_key, get_logger
   from ..shared.exceptions import AuthError, ValidationError

   _log = get_logger("mi_endpoint")

   def main(req: func.HttpRequest) -> func.HttpResponse:
       try:
           validate_api_key(req.headers.get("x-api-key"))
       except AuthError as exc:
           return func.HttpResponse(
               json.dumps({"error": str(exc), "code": exc.code}),
               status_code=401, mimetype="application/json",
           )

       _log.info("procesando solicitud", extra={"endpoint": "mi_endpoint"})
       # ... lógica de negocio ...

       return func.HttpResponse(json.dumps({"ok": True}), mimetype="application/json")
   ```

4. Ejecuta `func start` — la función aparece automáticamente sin tocar `host.json`.

## Convención de logs

Usa siempre el logger de `shared` para que los campos extra lleguen a Application Insights como `customDimensions`:

```python
from ..shared import get_logger

_log = get_logger("nombre_funcion")

# Correcto — campos en extra={} aparecen en customDimensions
_log.info("evento importante", extra={"cedula": cedula, "duracion_s": 1.2})

# Evitar — print() no pasa por el formatter estructurado
print("algo pasó")
```

Niveles de log:

| Nivel | Cuándo usarlo |
|---|---|
| `DEBUG` | Detalle técnico (valores de variables, pasos internos) |
| `INFO` | Flujo normal del negocio (request recibido, resultado OK) |
| `WARNING` | Situación recuperable (auth fallida, campo faltante) |
| `ERROR` | Excepción inesperada que aborta el request |

## Manejo de errores

Las excepciones en `shared/exceptions.py` tienen `code` y opcionalmente `field` para respuestas consistentes:

```python
from ..shared.exceptions import MotorError, ValidationError

# Lanza en lógica de negocio
raise ValidationError("El campo 'id' es requerido", field="id")
raise MotorError("Proveedor externo no respondió", code="PROVIDER_TIMEOUT")
```

Patrón de respuesta de error recomendado:

```python
except ValidationError as exc:
    return func.HttpResponse(
        json.dumps({"error": str(exc), "code": exc.code, "field": exc.field}),
        status_code=422, mimetype="application/json",
    )
except MotorError as exc:
    return func.HttpResponse(
        json.dumps({"error": str(exc), "code": exc.code}),
        status_code=500, mimetype="application/json",
    )
```

## CI/CD

El workflow `.github/workflows/deploy-azure-functions.yml` despliega automáticamente en cada push a `main`.

**Secret requerido en el repositorio:**

- `AZURE_CREDENTIALS` — JSON de Service Principal con rol `Contributor` sobre la Function App.

  ```bash
  az ad sp create-for-rbac \
    --name "coppovallio-github-actions" \
    --role contributor \
    --scopes /subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.Web/sites/coppovallio-api-prod \
    --sdk-auth
  ```
