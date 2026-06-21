from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.services.auth import derive_secret_key
from app.services.database_store import (
    delete_system_setting,
    load_system_setting,
    upsert_system_setting,
)


LLM_SETTING_KEY = "llm"


@dataclass(frozen=True)
class LlmProviderConfig:
    provider: str
    protocol: str
    label: str
    model: str
    base_url: str
    api_key: str
    source: str
    input_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    max_run_cost_usd: float | None = None


class SystemSettingDecryptionError(RuntimeError):
    pass


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {
        "label": "GPT / OpenAI",
        "protocol": "openai",
        "default_model": "gpt-4o-mini",
        "default_base_url": "https://api.openai.com/v1",
    },
    "deepseek": {
        "label": "DeepSeek",
        "protocol": "openai",
        "default_model": "deepseek-v4-flash",
        "default_base_url": "https://api.deepseek.com",
    },
    "gemini": {
        "label": "Google Gemini",
        "protocol": "openai",
        "default_model": "gemini-2.5-flash",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    },
    "anthropic": {
        "label": "Claude / Anthropic",
        "protocol": "anthropic",
        "default_model": "claude-3-5-sonnet-latest",
        "default_base_url": "https://api.anthropic.com",
    },
    "zhipu": {
        "label": "智谱 GLM",
        "protocol": "anthropic",
        "default_model": "glm-5",
        "default_base_url": "https://open.bigmodel.cn/api/anthropic",
    },
    "custom_openai": {
        "label": "自定义 OpenAI Compatible",
        "protocol": "openai",
        "default_model": "gpt-4o-mini",
        "default_base_url": "https://api.openai.com/v1",
    },
    "custom_anthropic": {
        "label": "自定义 Anthropic Compatible",
        "protocol": "anthropic",
        "default_model": "claude-3-5-sonnet-latest",
        "default_base_url": "https://api.anthropic.com",
    },
}


def _provider_preset(provider: str | None) -> dict[str, str]:
    return PROVIDER_PRESETS.get(str(provider or "").strip().lower(), PROVIDER_PRESETS["anthropic"])


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(derive_secret_key("system-settings:v1"))
    return Fernet(key)


def _environment_config() -> LlmProviderConfig | None:
    requested = os.getenv("OPPORTUNITY_OS_LLM_PROVIDER", "auto").strip().lower()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", "")).strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_AUTH_TOKEN", "")).strip()
    zhipu_key = os.getenv("ZHIPU_API_KEY", os.getenv("GLM_API_KEY", "")).strip()
    if requested in {"openai", "auto"} and openai_key:
        preset = PROVIDER_PRESETS["openai"]
        return LlmProviderConfig(
            provider="openai",
            protocol=preset["protocol"],
            label=preset["label"],
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            api_key=openai_key,
            source="environment",
            input_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_INPUT_USD_PER_MILLION"),
            output_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_OUTPUT_USD_PER_MILLION"),
            max_run_cost_usd=_optional_float("OPPORTUNITY_OS_LLM_MAX_RUN_COST_USD"),
        )
    if requested in {"deepseek", "auto"} and deepseek_key:
        preset = PROVIDER_PRESETS["deepseek"]
        return LlmProviderConfig(
            provider="deepseek",
            protocol=preset["protocol"],
            label=preset["label"],
            model=os.getenv("DEEPSEEK_MODEL", preset["default_model"]).strip(),
            base_url=os.getenv("DEEPSEEK_BASE_URL", preset["default_base_url"]).rstrip("/"),
            api_key=deepseek_key,
            source="environment",
            input_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_INPUT_USD_PER_MILLION"),
            output_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_OUTPUT_USD_PER_MILLION"),
            max_run_cost_usd=_optional_float("OPPORTUNITY_OS_LLM_MAX_RUN_COST_USD"),
        )
    if requested in {"gemini", "google", "auto"} and gemini_key:
        preset = PROVIDER_PRESETS["gemini"]
        return LlmProviderConfig(
            provider="gemini",
            protocol=preset["protocol"],
            label=preset["label"],
            model=os.getenv("GEMINI_MODEL", preset["default_model"]).strip(),
            base_url=os.getenv("GEMINI_BASE_URL", preset["default_base_url"]).rstrip("/"),
            api_key=gemini_key,
            source="environment",
            input_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_INPUT_USD_PER_MILLION"),
            output_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_OUTPUT_USD_PER_MILLION"),
            max_run_cost_usd=_optional_float("OPPORTUNITY_OS_LLM_MAX_RUN_COST_USD"),
        )
    if requested in {"anthropic", "auto"} and anthropic_key:
        preset = PROVIDER_PRESETS["anthropic"]
        model = (
            os.getenv("ANTHROPIC_MODEL")
            or os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL")
            or os.getenv("ANTHROPIC_DEFAULT_HAIKU_MODEL")
            or preset["default_model"]
        )
        return LlmProviderConfig(
            provider="anthropic",
            protocol=preset["protocol"],
            label=preset["label"],
            model=model.strip(),
            base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/"),
            api_key=anthropic_key,
            source="environment",
            input_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_INPUT_USD_PER_MILLION"),
            output_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_OUTPUT_USD_PER_MILLION"),
            max_run_cost_usd=_optional_float("OPPORTUNITY_OS_LLM_MAX_RUN_COST_USD"),
        )
    if requested in {"zhipu", "glm", "auto"} and zhipu_key:
        preset = PROVIDER_PRESETS["zhipu"]
        return LlmProviderConfig(
            provider="zhipu",
            protocol=preset["protocol"],
            label=preset["label"],
            model=os.getenv("ZHIPU_MODEL", os.getenv("GLM_MODEL", preset["default_model"])).strip(),
            base_url=os.getenv("ZHIPU_BASE_URL", preset["default_base_url"]).rstrip("/"),
            api_key=zhipu_key,
            source="environment",
            input_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_INPUT_USD_PER_MILLION"),
            output_usd_per_million=_optional_float("OPPORTUNITY_OS_LLM_OUTPUT_USD_PER_MILLION"),
            max_run_cost_usd=_optional_float("OPPORTUNITY_OS_LLM_MAX_RUN_COST_USD"),
        )
    return None


def _optional_float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def resolve_llm_config() -> LlmProviderConfig | None:
    record = load_system_setting(LLM_SETTING_KEY)
    if record:
        payload = dict(record["payload"])
        if not bool(payload.get("enabled", True)):
            return None
        preset = _provider_preset(str(payload.get("provider") or "anthropic"))
        encrypted = str(record.get("encrypted_secret") or "")
        if encrypted:
            try:
                api_key = _cipher().decrypt(encrypted.encode("ascii")).decode("utf-8")
            except (InvalidToken, ValueError, TypeError) as exc:
                raise SystemSettingDecryptionError("AI API 凭据无法解密，请重新配置") from exc
            return LlmProviderConfig(
                provider=str(payload.get("provider") or "anthropic"),
                protocol=str(payload.get("protocol") or preset["protocol"]),
                label=preset["label"],
                model=str(payload.get("model") or preset["default_model"]),
                base_url=str(payload.get("base_url") or preset["default_base_url"]).rstrip("/"),
                api_key=api_key,
                source="database",
                input_usd_per_million=_payload_float(payload.get("input_usd_per_million")),
                output_usd_per_million=_payload_float(payload.get("output_usd_per_million")),
                max_run_cost_usd=_payload_float(payload.get("max_run_cost_usd")),
            )
        environment = _environment_config()
        if environment:
            provider = str(payload.get("provider") or environment.provider)
            preset = _provider_preset(provider)
            return LlmProviderConfig(
                provider=provider,
                protocol=str(payload.get("protocol") or preset["protocol"]),
                label=preset["label"],
                model=str(payload.get("model") or environment.model),
                base_url=str(payload.get("base_url") or environment.base_url).rstrip("/"),
                api_key=environment.api_key,
                source="environment",
                input_usd_per_million=(
                    _payload_float(payload.get("input_usd_per_million"))
                    if payload.get("input_usd_per_million") is not None
                    else environment.input_usd_per_million
                ),
                output_usd_per_million=(
                    _payload_float(payload.get("output_usd_per_million"))
                    if payload.get("output_usd_per_million") is not None
                    else environment.output_usd_per_million
                ),
                max_run_cost_usd=(
                    _payload_float(payload.get("max_run_cost_usd"))
                    if payload.get("max_run_cost_usd") is not None
                    else environment.max_run_cost_usd
                ),
            )
    return _environment_config()


def _payload_float(value: Any) -> float | None:
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def llm_settings_status() -> dict[str, Any]:
    record = load_system_setting(LLM_SETTING_KEY)
    config = resolve_llm_config()
    payload = dict(record["payload"]) if record else {}
    return {
        "enabled": bool(payload.get("enabled", config is not None)),
        "configured": config is not None,
        "source": config.source if config else "none",
        "provider": config.provider if config else payload.get("provider"),
        "protocol": config.protocol if config else payload.get("protocol"),
        "provider_label": config.label if config else _provider_preset(payload.get("provider")).get("label"),
        "model": config.model if config else payload.get("model"),
        "base_url": config.base_url if config else payload.get("base_url"),
        "api_key_masked": _mask_key(config.api_key) if config else None,
        "input_usd_per_million": config.input_usd_per_million if config else payload.get("input_usd_per_million"),
        "output_usd_per_million": config.output_usd_per_million if config else payload.get("output_usd_per_million"),
        "max_run_cost_usd": config.max_run_cost_usd if config else payload.get("max_run_cost_usd"),
        "updated_at": record.get("updated_at") if record else None,
        "available_providers": [
            {"value": key, **value}
            for key, value in PROVIDER_PRESETS.items()
        ],
    }


def _mask_key(value: str) -> str:
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"


def save_llm_settings(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_system_setting(LLM_SETTING_KEY)
    environment = _environment_config()
    api_key = str(payload.pop("api_key", "") or "").strip()
    provider = str(payload.get("provider") or "").strip().lower()
    if provider not in PROVIDER_PRESETS:
        provider = "custom_openai"
    preset = _provider_preset(provider)
    payload["provider"] = provider
    payload["protocol"] = preset["protocol"]
    payload["model"] = str(payload.get("model") or preset["default_model"]).strip()
    payload["base_url"] = str(payload.get("base_url") or preset["default_base_url"]).strip().rstrip("/")
    encrypted = str(current.get("encrypted_secret") or "") if current else ""
    current_payload = dict(current.get("payload", {})) if current else {}
    if encrypted and not api_key and str(current_payload.get("provider") or "").strip().lower() not in {"", provider}:
        raise ValueError("切换 Provider 时必须输入新的 API Key，避免复用其他供应商的 Key")
    if api_key:
        encrypted = _cipher().encrypt(api_key.encode("utf-8")).decode("ascii")
    if payload.get("enabled", True) and not encrypted:
        if environment is None:
            raise ValueError("启用 AI Agent 时必须提供 API Key")
        if preset["protocol"] != environment.protocol:
            raise ValueError("切换到不同协议的 Provider 时必须提供对应的 API Key")
    upsert_system_setting(
        LLM_SETTING_KEY,
        encrypted_secret=encrypted or None,
        payload=payload,
    )
    return llm_settings_status()


def clear_llm_settings() -> dict[str, Any]:
    delete_system_setting(LLM_SETTING_KEY)
    return llm_settings_status()
