"""Provider-neutral routing for image-to-video generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "video-provider-routes.json"


class VideoProviderRouteError(ValueError):
    pass


class VideoProviderRouter:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = Path(config_path)
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise VideoProviderRouteError(f"invalid video provider route config: {error}") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("policy"), dict) or not isinstance(payload.get("providers"), list):
            raise VideoProviderRouteError("video provider route config is incomplete")
        self._policy = payload["policy"]
        self._providers = {str(item["id"]): item for item in payload["providers"]}

    def describe(self) -> dict[str, object]:
        return {
            "route_id": "VIDEO_PROVIDER_ROUTER",
            "default_provider": str(self._policy.get("default_provider") or ""),
            "billable_remote_call_requires_confirmation": bool(self._policy.get("billable_remote_call_requires_confirmation", True)),
            "human_review_required": bool(self._policy.get("human_review_required", True)),
            "providers": [
                {
                    "id": str(item.get("id") or ""),
                    "adapter": str(item.get("adapter") or ""),
                    "role": str(item.get("role") or ""),
                    "remote": bool(item.get("remote")),
                    "status": str(item.get("status") or ""),
                }
                for item in self._providers.values()
            ],
        }

    def route(
        self,
        capability: str,
        *,
        preferred_provider: str | None = None,
        available_provider_ids: Iterable[str] | None = None,
        confirm_billable: bool = False,
    ) -> dict[str, object]:
        capability = str(capability or "").strip()
        if not capability:
            raise VideoProviderRouteError("video capability is required")
        available = None if available_provider_ids is None else {str(item) for item in available_provider_ids}
        candidates = [
            item
            for item in self._providers.values()
            if str(item.get("status") or "") not in {"DISABLED", "BLOCKED"}
            and capability in item.get("capabilities", [])
            and (available is None or str(item.get("id")) in available)
        ]
        selected = None
        if preferred_provider:
            selected = next((item for item in candidates if item.get("id") == preferred_provider), None)
            if selected is None:
                raise VideoProviderRouteError(f"provider {preferred_provider} cannot serve {capability}")
        if selected is None:
            default_id = str(self._policy.get("default_provider") or "")
            selected = next((item for item in candidates if item.get("id") == default_id), None)
        if selected is None and candidates:
            selected = candidates[0]
        if selected is None:
            raise VideoProviderRouteError(f"no VideoProvider available for {capability}")
        if bool(selected.get("remote")) and self._policy.get("billable_remote_call_requires_confirmation") and not confirm_billable:
            raise VideoProviderRouteError("billable remote video generation requires explicit confirmation")
        return {
            "route_id": "VIDEO_PROVIDER_ROUTER",
            "provider_id": str(selected.get("id") or ""),
            "adapter": str(selected.get("adapter") or ""),
            "role": str(selected.get("role") or ""),
            "capability": capability,
            "remote": bool(selected.get("remote")),
            "human_review_required": bool(self._policy.get("human_review_required", True)),
        }


__all__ = ["VideoProviderRouteError", "VideoProviderRouter"]
