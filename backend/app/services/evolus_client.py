"""A small client for the Evolus REST API.

What it does:
  * sends a file to an Evolus document extractor and returns the JSON the extractor read
  * keeps a record of every call (address, time, status, duration) for the evolus_calls table
  * stays under the Evolus limit of 60 requests per minute, retries on 429 and 5xx errors
  * never logs the API key, the file contents or the response body

The address of the extract endpoint is configurable (EVOLUS_EXTRACT_PATH), because it must be
checked against the API reference inside the workspace.
"""
import os
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

import requests

DEFAULT_BASE_URL = "https://api.evolus.ai/api/v1"
DEFAULT_EXTRACT_PATH = "/agents/{agent_id}/json/{extractor_id}/ask-file"


class EvolusError(Exception):
    """An Evolus call failed. The message says what to do next and never contains secrets."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class CallRecord:
    called_at: str
    method: str
    endpoint: str
    http_status: Optional[int]
    duration_ms: int
    ok: bool
    shipment_id: Optional[str] = None
    document_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class RateLimiter:
    """Allows at most max_calls in any window of `period` seconds. Waits when the limit is reached."""

    def __init__(self, max_calls=60, period=60.0, clock=time.monotonic, sleep=time.sleep):
        self.max_calls, self.period, self.clock, self.sleep = max_calls, period, clock, sleep
        self._calls = deque()
        self._lock = Lock()

    def wait(self):
        with self._lock:
            now = self.clock()
            while self._calls and now - self._calls[0] >= self.period:
                self._calls.popleft()
            if len(self._calls) >= self.max_calls:
                self.sleep(self.period - (now - self._calls[0]))
                now = self.clock()
                while self._calls and now - self._calls[0] >= self.period:
                    self._calls.popleft()
            self._calls.append(self.clock())


class EvolusClient:
    def __init__(self, api_key, application_id, base_url=DEFAULT_BASE_URL, agent_id=None,
                 extract_path=DEFAULT_EXTRACT_PATH, timeout=120, max_retries=2, limiter=None,
                 session=None, sleep=time.sleep, on_call=None, params=None):
        if not api_key or not application_id:
            raise EvolusError("EVOLUS_API_KEY and EVOLUS_APPLICATION_ID must be set.")
        self._api_key = api_key
        self.application_id = application_id
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.extract_path = extract_path
        self.timeout, self.max_retries = timeout, max_retries
        self.limiter = limiter or RateLimiter()
        self.session = session or requests.Session()
        self._sleep = sleep
        self.on_call = on_call
        self.params = {"useWebhook": "false"} if params is None else params
        self.calls = []

    def __repr__(self):  # never show the key
        return f"EvolusClient(base_url={self.base_url!r}, application_id={self.application_id!r})"

    @classmethod
    def from_env(cls, env=None, **kwargs):
        env = os.environ if env is None else env
        missing = [k for k in ("EVOLUS_API_KEY", "EVOLUS_APPLICATION_ID") if not env.get(k)]
        if missing:
            raise EvolusError("Missing environment variables: " + ", ".join(missing))
        return cls(
            api_key=env["EVOLUS_API_KEY"], application_id=env["EVOLUS_APPLICATION_ID"],
            base_url=env.get("EVOLUS_BASE_URL") or DEFAULT_BASE_URL,
            agent_id=env.get("EVOLUS_AGENT_ID") or None,
            extract_path=env.get("EVOLUS_EXTRACT_PATH") or DEFAULT_EXTRACT_PATH, **kwargs)

    # ---------- public ----------
    def extract(self, extractor_id, file_path, agent_id=None, shipment_id=None, document_id=None):
        """Send one file to an extractor. Returns the JSON the extractor read, as Python data."""
        path = Path(file_path)
        if not path.is_file():
            raise EvolusError(f"File not found: {path.name}")
        if not extractor_id:
            raise EvolusError("No extractor id was given.")
        agent_id = agent_id or self.agent_id
        if not agent_id and "{agent_id}" in self.extract_path:
            raise EvolusError("No agent id was given (EVOLUS_AGENT_ID).")
        if ":" in str(extractor_id):      # "<extractor id>:<output structure id>", both copied from the Evolus API tab
            ext, out = str(extractor_id).split(":", 1)
            endpoint = f"/agents/{ext}/json/{out}/ask-file"
        else:
            endpoint = self.extract_path.format(agent_id=agent_id, extractor_id=extractor_id)
        return self._post_file(endpoint, path, shipment_id, document_id)

    # ---------- internals ----------
    def _headers(self):
        return {"X-ApiKey": self._api_key, "X-Application-Id": self.application_id, "Accept": "application/json"}

    def _record(self, endpoint, status, started, ok, shipment_id, document_id, error=None):
        rec = CallRecord(
            called_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), method="POST", endpoint=endpoint,
            http_status=status, duration_ms=int((time.monotonic() - started) * 1000), ok=ok,
            shipment_id=shipment_id, document_id=document_id, error=error)
        self.calls.append(rec)
        if self.on_call:
            self.on_call(rec)

    def _post_file(self, endpoint, path, shipment_id, document_id):
        url = self.base_url + endpoint
        last_error = None
        for attempt in range(self.max_retries + 1):
            self.limiter.wait()
            started = time.monotonic()
            try:
                with open(path, "rb") as f:
                    resp = self.session.post(url, headers=self._headers(), params=self.params,
                                             files={"file": (path.name, f, "application/pdf")}, timeout=self.timeout)
            except requests.Timeout:
                last_error = EvolusError("Evolus did not answer in time. Try again.")
                self._record(endpoint, None, started, False, shipment_id, document_id, "timeout")
            except requests.RequestException:
                last_error = EvolusError("Could not reach Evolus. Check the internet connection and EVOLUS_BASE_URL.")
                self._record(endpoint, None, started, False, shipment_id, document_id, "connection error")
            else:
                status = resp.status_code
                if 200 <= status < 300:
                    try:
                        data = resp.json()
                    except ValueError:
                        self._record(endpoint, status, started, False, shipment_id, document_id, "not json")
                        raise EvolusError("Evolus did not return valid JSON.", status)
                    self._record(endpoint, status, started, True, shipment_id, document_id)
                    return data
                self._record(endpoint, status, started, False, shipment_id, document_id, f"http {status}")
                if status in (401, 403):
                    raise EvolusError(f"Evolus refused the request ({status}). Check EVOLUS_API_KEY and EVOLUS_APPLICATION_ID.", status)
                if status == 402:
                    raise EvolusError("Evolus credits have run out (402). Check the credit balance in the workspace.", status)
                if status == 404:
                    raise EvolusError("Evolus could not find the extractor or agent (404). Check the ids and EVOLUS_EXTRACT_PATH.", status)
                if status == 429 or status >= 500:
                    last_error = EvolusError(f"Evolus is busy or failing ({status}).", status)
                    retry_after = resp.headers.get("Retry-After", "")
                    if retry_after.isdigit() and attempt < self.max_retries:
                        self._sleep(min(int(retry_after), 30))
                        continue
                else:
                    raise EvolusError(f"Evolus returned an unexpected status ({status}).", status)
            if attempt < self.max_retries:
                self._sleep(min(2 ** attempt, 8))
        raise last_error

