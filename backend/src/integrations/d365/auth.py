import os
import time
import requests

_token_cache = {"token": None, "expires_at": 0}


def get_d365_token():
    """Ambil access_token D365 via client_credentials, di-cache ~1 jam."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] - 60 > now:
        return _token_cache["token"]

    tenant = os.environ["D365_TENANT_ID"]
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/token"

    resp = requests.post(
        url,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["D365_CLIENT_ID"],
            "client_secret": os.environ["D365_CLIENT_SECRET"],
            "resource": os.environ["D365_RESOURCE"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _token_cache["token"]