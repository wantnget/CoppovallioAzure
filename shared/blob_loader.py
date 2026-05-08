import os
import json
from azure.storage.blob import BlobServiceClient, ContentSettings


def _get_blob_client(cedula, filename):
    conn = os.environ["BLOB_CONN_STRING"]
    container = os.environ.get("BLOB_CONTAINER", "motor-data")
    bsc = BlobServiceClient.from_connection_string(conn)
    cc = bsc.get_container_client(container)
    return cc.get_blob_client(f"{cedula}/{filename}")


def save_json_blob_by_id(cedula, filename, data):
    blob_client = _get_blob_client(cedula, filename)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    blob_client.upload_blob(
        payload,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json")
    )


def load_json_blob_by_id(cedula, filename):
    blob_client = _get_blob_client(cedula, filename)
    data = blob_client.download_blob().readall().decode("utf-8")
    return json.loads(data)
