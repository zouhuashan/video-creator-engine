"""Provider-neutral routing policy for final visual image generation.

This module is intentionally side-effect free: it never performs network calls.
It only selects an allowed Image Provider and enforces billing/upload gates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "visual-generation-routes.json"


class ImageProviderRouteError(ValueError):
    pass


class ImageProviderRouter:
    """Resolve final-visual work to an Image Provider without generating media."""

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = Path(config_path)
        self._payload = self._load()
        self._policy = self._payload["policy"]
        self._providers = {item["id"]: item for item in self._payload["providers"]}
        if self._policy.get("final_visual_route") != "IMAGE_PROVIDER_ROUTER":
            raise ImageProviderRouteError("final visual route must be IMAGE_PROVIDER_ROUTER")

    def _load(self) -> dict[str, object]:
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ImageProviderRouteError(f"invalid visual generation route config: {error}") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("policy"), dict) or not isinstance(payload.get("providers"), list):
            raise ImageProviderRouteError("visual generation route config is incomplete")
        return payload

    def describe(self) -> dict[str, object]:
        fallback_id = str(self._policy.get("high_quality_fallback_provider") or "")
        fallback = self._providers.get(fallback_id, {})
        blender = self._providers.get("BLENDER_ANIME", {})
        return {
            "final_visual_route": str(self._policy.get("final_visual_route") or ""),
            "provider_mode": str(self._policy.get("provider_mode") or ""),
            "default_local_provider": str(self._policy.get("default_local_provider") or ""),
            "high_quality_fallback_provider": fallback_id,
            "fallback_role": str(fallback.get("role") or ""),
            "human_review_required": bool(self._policy.get("human_review_required")),
            "billable_remote_call_requires_confirmation": bool(self._policy.get("billable_remote_call_requires_confirmation")),
            "reference_image_upload_requires_authorization": bool(self._policy.get("reference_image_upload_requires_authorization")),
            "generated_assets_root": str(self._policy.get("generated_assets_root") or "lookdev/image-studio"),
            "blender_role": str(blender.get("role") or ""),
            "blender_final_visual_allowed": str(blender.get("role") or "") != "AUXILIARY_3D_CONTROL",
        }

    @staticmethod
    def _is_final_visual_provider(provider: dict[str, object]) -> bool:
        return (
            str(provider.get("role") or "") != "AUXILIARY_3D_CONTROL"
            and str(provider.get("status") or "") in {"ACTIVE", "ACTIVE_FALLBACK", "AVAILABLE_WHEN_CONFIGURED"}
        )

    def route(
        self,
        capability: str,
        *,
        preferred_provider: str | None = None,
        available_provider_ids: Iterable[str] | None = None,
        confirm_billable: bool = False,
        reference_image: bool = False,
        upload_authorized: bool = False,
    ) -> dict[str, object]:
        capability = str(capability or "").strip()
        if not capability:
            raise ImageProviderRouteError("visual capability is required")
        available = None if available_provider_ids is None else {str(item) for item in available_provider_ids}
        candidates = [
            item for item in self._providers.values()
            if self._is_final_visual_provider(item)
            and capability in item.get("capabilities", [])
            and (available is None or str(item.get("id")) in available)
        ]
        selected = None
        if preferred_provider and str(preferred_provider).upper() != "AUTO":
            explicit = self._providers.get(str(preferred_provider))
            if explicit is None:
                raise ImageProviderRouteError(f"unknown image provider: {preferred_provider}")
            if explicit not in candidates:
                raise ImageProviderRouteError(f"provider {preferred_provider} cannot serve final visual capability {capability}")
            selected = explicit
        else:
            local_id = self._policy.get("default_local_provider")
            if local_id:
                selected = next((item for item in candidates if item.get("id") == local_id), None)
            default_id = self._policy.get("default_remote_provider")
            if selected is None and default_id:
                selected = next((item for item in candidates if item.get("id") == default_id), None)
            if selected is None:
                fallback_id = self._policy.get("high_quality_fallback_provider")
                selected = next((item for item in candidates if item.get("id") == fallback_id), None)
            if selected is None and candidates:
                selected = candidates[0]
        if selected is None:
            raise ImageProviderRouteError(f"no final visual Image Provider available for {capability}")
        if bool(selected.get("remote")) and self._policy.get("billable_remote_call_requires_confirmation") and not confirm_billable:
            raise ImageProviderRouteError("billable remote image generation requires explicit confirmation")
        if reference_image and self._policy.get("reference_image_upload_requires_authorization") and not upload_authorized:
            raise ImageProviderRouteError("reference image upload requires explicit authorization")
        fallback_chain = []
        for provider_id in (self._policy.get("default_local_provider"), self._policy.get("default_remote_provider"), self._policy.get("high_quality_fallback_provider")):
            if provider_id and provider_id not in fallback_chain:
                fallback_chain.append(str(provider_id))
        return {
            "route_id": "IMAGE_PROVIDER_ROUTER",
            "provider_id": str(selected.get("id") or ""),
            "adapter": str(selected.get("adapter") or ""),
            "role": str(selected.get("role") or ""),
            "capability": capability,
            "remote": bool(selected.get("remote")),
            "human_review_required": bool(self._policy.get("human_review_required")),
            "generated_assets_root": str(self._policy.get("generated_assets_root") or "lookdev/image-studio"),
            "fallback_chain": fallback_chain,
        }


__all__ = ["ImageProviderRouteError", "ImageProviderRouter"]
