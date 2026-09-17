"""
HTTP client from the kiosk agent to the Core API.

Communication failures are never guessed at: anything other than a clear
HTTP answer from the Core API raises CoreUnavailable, and callers must treat
that as "we don't know / nothing happened" - never as success.

The transport is replaceable so tests can run the real Core API in-process.
"""
import logging

import requests

log = logging.getLogger("autorefund.agent.core")


class CoreUnavailable(Exception):
    """The Core API could not be reached or did not give a usable answer."""


class CoreResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body if isinstance(body, dict) else {}

    @property
    def ok(self):
        return 200 <= self.status < 300


class RequestsTransport:
    def __init__(self, base_url, timeout):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def send(self, method, path, headers=None, json=None, data=None, files=None):
        response = self.session.request(method, self.base_url + path, headers=headers, json=json,
                                        data=data, files=files, timeout=self.timeout)
        try:
            body = response.json()
        except ValueError:
            body = None
        return response.status_code, body


class CoreApiClient:
    def __init__(self, base_url=None, timeout=10, transport=None):
        self.transport = transport or RequestsTransport(base_url, timeout)

    def call(self, identity, method, path, *, headers=None, json=None, data=None, files=None):
        all_headers = dict(identity.auth_headers())
        all_headers.update(headers or {})
        try:
            status, body = self.transport.send(method, path, headers=all_headers, json=json,
                                               data=data, files=files)
        except requests.RequestException as exc:
            log.warning("Core API unreachable: %s %s (%s)", method, path, exc.__class__.__name__)
            raise CoreUnavailable(str(exc)) from exc
        if status >= 500 or not isinstance(body, dict):
            log.warning("Core API gave no usable answer: %s %s -> %s", method, path, status)
            raise CoreUnavailable(f"HTTP {status}")
        return CoreResponse(status, body)
