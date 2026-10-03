"""Read-only Freqtrade telemetry; no order/configuration method is exposed."""
import base64
import json
import os
import urllib.parse
import urllib.request


class TelemetryError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ReadOnlyAPI:
    ENDPOINTS = frozenset({"show_config", "balance", "profit", "status"})

    def __init__(self, url=None, username=None, password=None, opener=None):
        self.url = (url or os.environ.get("FREQTRADE_API_URL", "")).rstrip("/")
        self.username = username if username is not None else os.environ.get("FREQTRADE_API_USERNAME", "")
        self.password = password if password is not None else os.environ.get("FREQTRADE_API_PASSWORD", "")
        self.opener = opener or urllib.request.build_opener(NoRedirect()).open
        parsed = urllib.parse.urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"freqtrade", "127.0.0.1", "localhost"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise TelemetryError("api_url_not_local")

    def get(self, endpoint):
        if endpoint not in self.ENDPOINTS:
            raise TelemetryError("endpoint_not_read_only")
        token = base64.b64encode((self.username + ":" + self.password).encode()).decode()
        request = urllib.request.Request(self.url + "/api/v1/" + endpoint, headers={"Authorization": "Basic " + token}, method="GET")
        try:
            with self.opener(request, timeout=4) as response:
                payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise TelemetryError("api_response_too_large")
            result = json.loads(payload)
            if not isinstance(result, list if endpoint == "status" else dict):
                raise ValueError("response_shape")
            return result
        except TelemetryError:
            raise
        except Exception as exc:
            # Never expose exception content: it may contain credentials.
            raise TelemetryError("api_" + type(exc).__name__) from None

    def snapshot(self):
        return {endpoint: self.get(endpoint) for endpoint in sorted(self.ENDPOINTS)}
