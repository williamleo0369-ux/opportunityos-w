from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app.schemas import (
    Competitor,
    InnovationIdea,
    Opportunity,
    PainPoint,
    Patent,
    Report,
    SearchTask,
    SupplyChainItem,
    TrendData,
)
from app.services.database_store import database_is_empty, database_status, load_payload, save_payload


def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "apps" / "api").exists() or (parent / "package.json").exists():
            return parent
    return current.parents[2]


PROJECT_ROOT = _find_project_root()
LEGACY_STORE_PATH = PROJECT_ROOT / ".opportunity-os-data" / "store.json"
STORE_PATH = Path(os.environ.get("OPPORTUNITY_OS_STORE_PATH", Path.home() / ".opportunity-os" / "store.json")).expanduser()

ModelT = TypeVar("ModelT", bound=BaseModel)


def empty_state() -> dict[str, Any]:
    return {
        "tasks": {},
        "opportunities": {},
        "trends": {},
        "patents": {},
        "competitors": {},
        "pain_points": {},
        "supply_chain": {},
        "innovation_ideas": {},
        "reports": {},
        "saved": {},
        "source_health_history": [],
    }


def _dump_model_map(rows: dict[str, BaseModel]) -> dict[str, Any]:
    return {key: value.model_dump(mode="json") for key, value in rows.items()}


def _dump_model_list_map(rows: dict[str, list[BaseModel]]) -> dict[str, Any]:
    return {key: [value.model_dump(mode="json") for value in values] for key, values in rows.items()}


def _load_model_map(raw: dict[str, Any], model: type[ModelT]) -> dict[str, ModelT]:
    return {key: model.model_validate(value) for key, value in raw.items()}


def _load_model_list_map(raw: dict[str, Any], model: type[ModelT]) -> dict[str, list[ModelT]]:
    return {key: [model.model_validate(value) for value in values] for key, values in raw.items()}


def store_status() -> dict[str, Any]:
    status = database_status()
    return {
        **status,
        "json_path": str(STORE_PATH),
        "legacy_path": str(LEGACY_STORE_PATH),
        "json_exists": STORE_PATH.exists(),
        "legacy_exists": LEGACY_STORE_PATH.exists(),
    }


def _read_legacy_payload() -> tuple[dict[str, Any], str | None]:
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text()), str(STORE_PATH)
        except (json.JSONDecodeError, OSError):
            return {}, None

    if LEGACY_STORE_PATH.exists():
        try:
            raw = json.loads(LEGACY_STORE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}, None
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STORE_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
        return raw, str(LEGACY_STORE_PATH)

    return {}, None


def load_state() -> dict[str, Any]:
    if database_is_empty():
        legacy_payload, migration_source = _read_legacy_payload()
        if legacy_payload:
            save_payload(legacy_payload, migration_source=migration_source)

    raw = load_payload()
    if not raw:
        return empty_state()

    return {
        "tasks": _load_model_map(raw.get("tasks", {}), SearchTask),
        "opportunities": _load_model_map(raw.get("opportunities", {}), Opportunity),
        "trends": _load_model_list_map(raw.get("trends", {}), TrendData),
        "patents": _load_model_list_map(raw.get("patents", {}), Patent),
        "competitors": _load_model_list_map(raw.get("competitors", {}), Competitor),
        "pain_points": _load_model_list_map(raw.get("pain_points", {}), PainPoint),
        "supply_chain": _load_model_list_map(raw.get("supply_chain", {}), SupplyChainItem),
        "innovation_ideas": _load_model_list_map(raw.get("innovation_ideas", {}), InnovationIdea),
        "reports": _load_model_map(raw.get("reports", {}), Report),
        "saved": raw.get("saved", {}),
        "source_health_history": raw.get("source_health_history", []),
    }


def build_state_payload(
    *,
    tasks: dict[str, SearchTask],
    opportunities: dict[str, Opportunity],
    trends: dict[str, list[TrendData]],
    patents: dict[str, list[Patent]],
    competitors: dict[str, list[Competitor]],
    pain_points: dict[str, list[PainPoint]],
    supply_chain: dict[str, list[SupplyChainItem]],
    innovation_ideas: dict[str, list[InnovationIdea]],
    reports: dict[str, Report],
    saved: dict[str, dict[str, str | None]],
    source_health_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "tasks": _dump_model_map(tasks),
        "opportunities": _dump_model_map(opportunities),
        "trends": _dump_model_list_map(trends),
        "patents": _dump_model_list_map(patents),
        "competitors": _dump_model_list_map(competitors),
        "pain_points": _dump_model_list_map(pain_points),
        "supply_chain": _dump_model_list_map(supply_chain),
        "innovation_ideas": _dump_model_list_map(innovation_ideas),
        "reports": _dump_model_map(reports),
        "saved": saved,
        "source_health_history": source_health_history or [],
    }


def save_state(
    *,
    tasks: dict[str, SearchTask],
    opportunities: dict[str, Opportunity],
    trends: dict[str, list[TrendData]],
    patents: dict[str, list[Patent]],
    competitors: dict[str, list[Competitor]],
    pain_points: dict[str, list[PainPoint]],
    supply_chain: dict[str, list[SupplyChainItem]],
    innovation_ideas: dict[str, list[InnovationIdea]],
    reports: dict[str, Report],
    saved: dict[str, dict[str, str | None]],
    source_health_history: list[dict[str, Any]] | None = None,
) -> None:
    payload = build_state_payload(
        tasks=tasks,
        opportunities=opportunities,
        trends=trends,
        patents=patents,
        competitors=competitors,
        pain_points=pain_points,
        supply_chain=supply_chain,
        innovation_ideas=innovation_ideas,
        reports=reports,
        saved=saved,
        source_health_history=source_health_history,
    )
    save_payload(payload)
