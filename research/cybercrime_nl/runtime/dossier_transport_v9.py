"""Same bounded wire transport with fixed, source-free failure-stage metadata."""
import json
import os
import urllib.error
import urllib.request

import dossier_transport as original
from newsresearch.common import ResearchError, canonical, require_no_credentials
from newsresearch.gateway import ProviderResponse

OBSERVABILITY = "dossier-transport-fixed-stage-codes-v1"
STAGES = {"request_preflight", "before_dispatch", "open", "status", "read", "decode", "response_credentials", "json", "complete"}
ERROR_CODES = {"request_preflight_rejected", "dispatch_stopped", "redirect_rejected", "http_status_unavailable", "response_byte_capacity",
    "response_content_rejected", "response_decode_failed", "network_url_error", "network_connection_reset",
    "network_disconnected", "network_timeout", "transport_other_failure"}


class FixedFailure(ResearchError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FixedFailure("redirect_rejected")


def failure_code(error, stage):
    if isinstance(error, FixedFailure) and str(error) in ERROR_CODES:
        return str(error)
    if stage == "response_credentials":
        return "response_content_rejected"
    if isinstance(error, UnicodeError):
        return "response_decode_failed"
    if isinstance(error, urllib.error.URLError):
        return "network_url_error"
    if isinstance(error, ConnectionResetError):
        return "network_connection_reset"
    if type(error).__name__ == "RemoteDisconnected":
        return "network_disconnected"
    if isinstance(error, TimeoutError):
        return "network_timeout"
    return "transport_other_failure"


class UnifiedTransport(original.UnifiedTransport):
    """No retries, wire changes, relaxed content guards or unsafe exception text."""
    def complete_prepared(self, invocation):
        try:
            manifest = invocation.manifest()
            require_no_credentials(invocation.request)
            model = invocation.request.get("model")
            expected = {"decisions": {"gpt-6-luna"}, "responses": {"gpt-6-luna", "gpt-6-astra"},
                        "embeddings": {"text-embedding-3-large"}}
            if model not in expected[invocation.kind]:
                raise ResearchError("dossier_transport_model_invalid")
            key = os.environ.get("OPENAI_API_KEY")
            if not key or any(c in key for c in "\r\n"):
                raise ResearchError("dossier_key_unavailable")
            wire = canonical(invocation.request).encode("utf-8")
            if len(wire) > original.MAX_REQUEST_BYTES:
                raise ResearchError("dossier_request_byte_capacity")
            request = urllib.request.Request(manifest["url"], data=wire, method="POST", headers={
                "Authorization": "Bearer " + key, "Content-Type": "application/json",
                "X-Client-Request-Id": invocation.client_id})
            opener = self.opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        except (ResearchError, KeyError, TypeError, ValueError):
            return ProviderResponse(None, "openai-" + getattr(invocation, "kind", "unavailable"), None, raw_response={
                "unknown_outcome": False, "dispatch_started": False, "http_status": None,
                "observability_version": OBSERVABILITY, "failure_stage": "request_preflight",
                "failure_code": "request_preflight_rejected"})
        response, started, status, stage = None, False, None, "before_dispatch"
        try:
            if self.before_dispatch is not None:
                with self._dispatch_lock:
                    if self.before_dispatch(invocation) is False:
                        raise FixedFailure("dispatch_stopped")
            started, stage = True, "open"
            try:
                response = opener.open(request, timeout=120)
            except urllib.error.HTTPError as error:
                response = error
            stage = "status"
            status = response.status
            if type(status) is not int:
                status = None
                raise FixedFailure("http_status_unavailable")
            stage = "read"
            raw = response.read(original.MAX_RESPONSE_BYTES + 1)
            if len(raw) > original.MAX_RESPONSE_BYTES:
                raise FixedFailure("response_byte_capacity")
            stage = "decode"
            text = raw.decode("utf-8")
            stage = "response_credentials"
            require_no_credentials(text)
            stage = "json"
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if payload is not None and not isinstance(payload, dict):
                payload = None
            metadata = {"http_status": status, "response_text": text, "kind": invocation.kind,
                "unknown_outcome": status >= 500 or payload is None, "dispatch_started": True,
                "observability_version": OBSERVABILITY, "failure_stage": "complete", "failure_code": None}
            return ProviderResponse(payload if status == 200 else None, "openai-" + invocation.kind,
                payload.get("model") if payload else None, response.headers.get("x-request-id"),
                payload.get("usage") if status == 200 and payload else None, metadata)
        except Exception as error:
            code = failure_code(error, stage)
            return ProviderResponse(None, "openai-" + invocation.kind, None, raw_response={
                "unknown_outcome": started, "dispatch_started": started, "kind": invocation.kind,
                "http_status": status, "observability_version": OBSERVABILITY,
                "failure_stage": stage, "failure_code": code})
        finally:
            if response is not None:
                response.close()
