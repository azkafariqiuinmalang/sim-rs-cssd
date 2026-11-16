import json
from time import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


class AuthUnavailable(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Credentials must stay on the configured Supabase endpoint.
        return None


def validate_url(url):
    parsed = urlsplit(url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (not parsed.hostname or parsed.username is not None or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))):
        raise ValueError("Gunakan URL proyek Supabase HTTPS, atau URL HTTP localhost untuk demo.")


def sign_in(url, api_key, email, password):
    request = Request(
        url.rstrip("/") + "/auth/v1/token?grant_type=password",
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"apikey": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with build_opener(NoRedirect).open(request, timeout=8) as response:
            payload = json.load(response)
        if not payload.get("access_token") or not payload["user"].get("email_confirmed_at"):
            return None
        expires_in = int(payload["expires_in"])
        if expires_in <= 0:
            raise AuthUnavailable
        return str(UUID(payload["user"]["id"])), int(time()) + min(expires_in, 3600)
    except HTTPError as exc:
        if exc.code in {400, 401, 422}:
            return None
        raise AuthUnavailable from None
    except (URLError, TimeoutError, ValueError, KeyError, TypeError, AttributeError):
        raise AuthUnavailable from None
