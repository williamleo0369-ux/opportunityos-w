from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class UsagePolicyPreset:
    plan: str
    label: str
    search_quota_daily: int
    report_quota_monthly: int
    ai_cost_quota_monthly: float | None


def _env_int(name: str, default: int, *, legacy_name: str | None = None) -> int:
    raw = os.getenv(name)
    if raw is None and legacy_name:
        raw = os.getenv(legacy_name)
    if raw is None:
        raw = str(default)
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _env_optional_float(
    name: str,
    default: float | None,
    *,
    legacy_name: str | None = None,
) -> float | None:
    raw = os.getenv(name)
    if raw is None and legacy_name:
        raw = os.getenv(legacy_name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"", "none", "null", "unlimited"}:
        return None
    try:
        return max(0.0, float(normalized))
    except ValueError:
        return default


def usage_policy_presets() -> list[dict[str, int | float | str | None]]:
    presets = [
        UsagePolicyPreset(
            plan="starter",
            label="Starter",
            search_quota_daily=_env_int(
                "OPPORTUNITY_OS_STARTER_SEARCH_QUOTA_DAILY",
                20,
                legacy_name="OPPORTUNITY_OS_DEFAULT_SEARCH_QUOTA_DAILY",
            ),
            report_quota_monthly=_env_int(
                "OPPORTUNITY_OS_STARTER_REPORT_QUOTA_MONTHLY",
                100,
                legacy_name="OPPORTUNITY_OS_DEFAULT_REPORT_QUOTA_MONTHLY",
            ),
            ai_cost_quota_monthly=_env_optional_float(
                "OPPORTUNITY_OS_STARTER_AI_COST_QUOTA_MONTHLY",
                5.0,
                legacy_name="OPPORTUNITY_OS_DEFAULT_AI_COST_QUOTA_MONTHLY",
            ),
        ),
        UsagePolicyPreset(
            plan="pro",
            label="Pro",
            search_quota_daily=_env_int("OPPORTUNITY_OS_PRO_SEARCH_QUOTA_DAILY", 100),
            report_quota_monthly=_env_int("OPPORTUNITY_OS_PRO_REPORT_QUOTA_MONTHLY", 500),
            ai_cost_quota_monthly=_env_optional_float("OPPORTUNITY_OS_PRO_AI_COST_QUOTA_MONTHLY", 25.0),
        ),
        UsagePolicyPreset(
            plan="admin",
            label="Admin",
            search_quota_daily=_env_int("OPPORTUNITY_OS_ADMIN_SEARCH_QUOTA_DAILY", 100000),
            report_quota_monthly=_env_int("OPPORTUNITY_OS_ADMIN_REPORT_QUOTA_MONTHLY", 100000),
            ai_cost_quota_monthly=_env_optional_float("OPPORTUNITY_OS_ADMIN_AI_COST_QUOTA_MONTHLY", None),
        ),
    ]
    return [asdict(item) for item in presets]


def usage_policy_for_plan(plan: str | None) -> dict[str, int | float | str | None] | None:
    normalized = str(plan or "").strip().lower()
    for preset in usage_policy_presets():
        if preset["plan"] == normalized:
            return preset
    return None


def default_usage_policy() -> dict[str, int | float | str | None]:
    return usage_policy_for_plan("starter") or usage_policy_presets()[0]
