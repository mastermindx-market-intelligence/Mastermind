"""Executive MCP projection for read-only Mosyle telemetry."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from integrations.executive_mcp import schemas as legacy
from integrations.executive_mcp.web_ceo_v3 import (
    MDM_TOOL_NAME,
    WEB_CEO_V3_SERVER_VERSION,
    validate_web_ceo_v3_tool_arguments,
)
from integrations.mastermind_executive_app.gateway import (
    WebCeoV2CeoIngressReadGateway,
)
from integrations.mosyle_mdm.client import MosyleTelemetryError

MAX_MDM_RESULT_BYTES = 128 * 1024

_ERROR_MAP = {
    "invalid_input": "invalid_input",
    "not_found": "not_found",
    "ambiguous_device": "invalid_input",
    "output_too_large": "output_too_large",
    "credential_refused": "backend_refused",
    "credential_unavailable": "backend_unavailable",
    "provider_unavailable": "backend_unavailable",
    "invalid_response": "backend_unavailable",
    "clock_unavailable": "backend_unavailable",
}


class WebCeoV3CeoIngressReadGateway(WebCeoV2CeoIngressReadGateway):
    """V2 Executive reads plus one local external-sensor observation."""

    _READ_TOOL_NAMES = WebCeoV2CeoIngressReadGateway._READ_TOOL_NAMES + (
        MDM_TOOL_NAME,
    )

    def __init__(self, socket_path, client, *, mdm_reader: Any) -> None:
        super().__init__(socket_path, client)
        if mdm_reader is None or not callable(
            getattr(mdm_reader, "list_macos_devices", None)
        ):
            raise ValueError("Mosyle telemetry reader is unavailable")
        self._mdm_reader = mdm_reader

    def _validate_arguments(
        self, name: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        return validate_web_ceo_v3_tool_arguments(name, arguments)

    async def call(
        self, name: str, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        if name != MDM_TOOL_NAME:
            envelope = await super().call(name, arguments)
            envelope["server_version"] = WEB_CEO_V3_SERVER_VERSION
            return envelope

        generated_at = datetime.now(timezone.utc).isoformat()
        try:
            validated = self._validate_arguments(name, arguments)
            if validated["view"] == "fleet":
                data = await self._mdm_reader.list_macos_devices()
            else:
                data = await self._mdm_reader.device(
                    serial_number=validated.get("serial_number"),
                    hostname=validated.get("hostname"),
                )
            if len(legacy.canonical_json(data)) > MAX_MDM_RESULT_BYTES:
                raise MosyleTelemetryError(
                    "output_too_large", "Mosyle telemetry exceeds the MCP result budget"
                )
            envelope = legacy.result_envelope(
                name,
                mode=legacy.ServerMode.READONLY,
                generated_at=generated_at,
                data=data,
                grounding={
                    "mdm": "mosyle_business",
                    "authority": "external_observation_only",
                },
            )
        except MosyleTelemetryError as exc:
            envelope = legacy.error_envelope(
                name,
                mode=legacy.ServerMode.READONLY,
                generated_at=generated_at,
                code=_ERROR_MAP.get(exc.code, "backend_unavailable"),
                message=exc.message,
                grounding={
                    "mdm": "mosyle_business",
                    "authority": "external_observation_only",
                },
            )
        except legacy.GatewayError as exc:
            envelope = legacy.error_envelope(
                name,
                mode=legacy.ServerMode.READONLY,
                generated_at=generated_at,
                code=exc.code,
                message=exc.message,
                grounding={
                    "mdm": "mosyle_business",
                    "authority": "external_observation_only",
                },
            )
        except Exception:
            envelope = legacy.error_envelope(
                name,
                mode=legacy.ServerMode.READONLY,
                generated_at=generated_at,
                code="backend_unavailable",
                message="Mosyle telemetry is unavailable",
                grounding={
                    "mdm": "mosyle_business",
                    "authority": "external_observation_only",
                },
            )
        envelope["server_version"] = WEB_CEO_V3_SERVER_VERSION
        return envelope
