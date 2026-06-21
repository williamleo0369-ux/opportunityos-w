from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.services.system_settings import LlmProviderConfig, resolve_llm_config


SSL_CONTEXT = ssl._create_unverified_context()


def llm_timeout_seconds() -> int:
    raw = os.getenv("OPPORTUNITY_OS_LLM_TIMEOUT_SECONDS", "25").strip()
    try:
        return max(5, min(120, int(raw)))
    except ValueError:
        return 25


def agent_parallelism() -> int:
    raw = os.getenv("OPPORTUNITY_OS_AGENT_PARALLELISM", "1").strip()
    try:
        return max(1, min(3, int(raw)))
    except ValueError:
        return 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentIdea:
    title: str
    description: str
    market_value_score: int
    difficulty_score: int
    cost_impact: str
    differentiation_score: int
    target_user: str
    suggested_features: list[str]


@dataclass
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int
    request_id: str | None
    latency_ms: int


@dataclass
class AgentStep:
    name: str
    label: str
    status: str
    started_at: str
    finished_at: str
    duration_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    request_id: str | None = None
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "request_id": self.request_id,
            "error": self.error,
            "output": self.output,
        }


@dataclass
class AgentResult:
    run_id: str
    mode: str
    provider: str | None
    model: str | None
    status: str
    error: str | None
    started_at: str
    finished_at: str | None = None
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    executive_summary: str | None = None
    final_recommendation: str | None = None
    market_analysis: str | None = None
    trend_analysis: str | None = None
    patent_analysis: str | None = None
    competitor_analysis: str | None = None
    pain_point_analysis: str | None = None
    supply_chain_analysis: str | None = None
    innovation_analysis: str | None = None
    score_reasoning: str | None = None
    risk_notice: str | None = None
    evidence_gaps: list[str] = field(default_factory=list)
    ideas: list[AgentIdea] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    provider_config: LlmProviderConfig | None = field(default=None, repr=False)

    def to_trace(self) -> dict[str, Any]:
        return {
            "id": self.run_id,
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "score_reasoning": self.score_reasoning,
            "risk_notice": self.risk_notice,
            "evidence_gaps": self.evidence_gaps,
            "steps": [step.to_dict() for step in self.steps],
        }


def llm_status() -> dict[str, Any]:
    config = resolve_llm_config()
    if config is None:
        return {
            "available": False,
            "status": "missing_credentials",
            "provider": None,
            "model": None,
            "orchestration": "multi_stage",
            "reason": "Set OPENAI_API_KEY or ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN to enable the LLM agent.",
        }
    return {
        "available": True,
        "status": "configured",
        "provider": config.provider,
        "model": config.model,
        "source": config.source,
        "orchestration": "multi_stage",
        "reason": "Five-stage evidence analysis, innovation, scoring and report orchestration is configured.",
    }


def run_opportunity_analysis(context: dict[str, Any]) -> AgentResult:
    started_at = utc_now_iso()
    started = time.perf_counter()
    config = resolve_llm_config()
    if config is None:
        return _empty_result("disabled", None, None, "missing_credentials", None, started_at, started)

    result = AgentResult(
        run_id=str(uuid4()),
        mode="multi_agent",
        provider=config.provider,
        model=config.model,
        status="running",
        error=None,
        started_at=started_at,
        provider_config=config,
    )
    stage_specs = [
        (
            "trend_market",
            "趋势与市场 Agent",
            _trend_market_prompt(context),
            {"market_analysis", "trend_analysis"},
        ),
        (
            "patent_risk",
            "专利风险 Agent",
            _patent_prompt(context),
            {"patent_analysis"},
        ),
        (
            "commercial_evidence",
            "竞品、痛点与供应链 Agent",
            _commercial_prompt(context),
            {"competitor_analysis", "pain_point_analysis", "supply_chain_analysis"},
        ),
    ]
    if config.max_run_cost_usd is not None:
        for name, label, prompt, required in stage_specs:
            max_tokens = 850
            if _would_exceed_budget(result, config, prompt, max_tokens):
                result.steps.append(_budget_skipped_step(name, label, config))
                continue
            result.steps.append(_run_stage(config, name, label, prompt, required, max_tokens))
    else:
        with ThreadPoolExecutor(max_workers=agent_parallelism()) as executor:
            futures = {
                executor.submit(
                    _run_stage,
                    config,
                    name,
                    label,
                    prompt,
                    required,
                    850,
                ): name
                for name, label, prompt, required in stage_specs
            }
            for future in as_completed(futures):
                result.steps.append(future.result())

    result.steps.sort(key=lambda step: [item[0] for item in stage_specs].index(step.name))
    _apply_specialist_outputs(result)

    completed_specialists = sum(1 for step in result.steps if step.status == "completed")
    if completed_specialists:
        innovation_prompt = _innovation_prompt(context, result)
        innovation_step = (
            _budget_skipped_step("innovation", "创新方向 Agent", config)
            if _would_exceed_budget(result, config, innovation_prompt, 1200)
            else _run_stage(
                config,
                "innovation",
                "创新方向 Agent",
                innovation_prompt,
                {"innovation_analysis", "ideas"},
                1200,
            )
        )
        result.steps.append(innovation_step)
        if innovation_step.status == "completed":
            result.innovation_analysis = _text(innovation_step.output.get("innovation_analysis"))
            result.ideas = _ideas_from_payload(innovation_step.output)
    else:
        result.steps.append(_skipped_step("innovation", "创新方向 Agent", "No specialist Agent completed."))

    _finish_result(result, started)
    budget_limited = any(_is_budget_skip(step) for step in result.steps)
    result.status = (
        "analysis_completed"
        if completed_specialists == len(stage_specs) and result.ideas
        else "analysis_completed_with_gaps"
        if completed_specialists or budget_limited
        else "provider_error"
    )
    errors = [step.error for step in result.steps if step.error]
    result.error = "; ".join(errors)[:800] if errors else None
    return result


def finalize_opportunity_agent(
    context: dict[str, Any],
    result: AgentResult,
    scores: dict[str, int | str],
    ideas: list[dict[str, Any]],
) -> AgentResult:
    if not result.provider or result.status in {"missing_credentials", "provider_error"}:
        if not any(step.name == "scoring_report" for step in result.steps):
            result.steps.append(_skipped_step("scoring_report", "评分与报告 Agent", "No usable Agent analysis was available."))
            _finish_result(result, time.perf_counter(), accumulate=True)
        return result
    started = time.perf_counter()
    config = result.provider_config or resolve_llm_config()
    report_prompt = _report_prompt(context, result, scores, ideas)
    report_step = (
        _budget_skipped_step("scoring_report", "评分与报告 Agent", config)
        if _would_exceed_budget(result, config, report_prompt, 1100)
        else _run_stage(
            config,
            "scoring_report",
            "评分与报告 Agent",
            report_prompt,
            {"executive_summary", "final_recommendation", "score_reasoning", "risk_notice"},
            1100,
        )
    )
    result.steps.append(report_step)
    if report_step.status == "completed":
        result.executive_summary = _text(report_step.output.get("executive_summary"))
        result.final_recommendation = _text(report_step.output.get("final_recommendation"))
        result.score_reasoning = _text(report_step.output.get("score_reasoning"))
        result.risk_notice = _text(report_step.output.get("risk_notice"))
    _finish_result(result, started, accumulate=True)
    completed = sum(1 for step in result.steps if step.status == "completed")
    result.status = "completed" if completed == 5 else "completed_with_gaps"
    errors = [step.error for step in result.steps if step.error]
    result.error = "; ".join(errors)[:800] if errors else None
    return result


def run_opportunity_agent(context: dict[str, Any]) -> AgentResult:
    result = run_opportunity_analysis(context)
    return finalize_opportunity_agent(context, result, {}, [])


def skipped_agent_result(reason: str) -> AgentResult:
    started_at = utc_now_iso()
    started = time.perf_counter()
    result = AgentResult(
        run_id=str(uuid4()),
        mode="budget_guard",
        provider=None,
        model=None,
        status="completed_with_gaps",
        error=reason,
        started_at=started_at,
    )
    result.steps.append(_skipped_step("ai_budget_guard", "AI 成本护栏", reason))
    _finish_result(result, started)
    return result


def _apply_specialist_outputs(result: AgentResult) -> None:
    for step in result.steps:
        if step.status != "completed":
            continue
        output = step.output
        if step.name == "trend_market":
            result.market_analysis = _text(output.get("market_analysis"))
            result.trend_analysis = _text(output.get("trend_analysis"))
        elif step.name == "patent_risk":
            result.patent_analysis = _text(output.get("patent_analysis"))
        elif step.name == "commercial_evidence":
            result.competitor_analysis = _text(output.get("competitor_analysis"))
            result.pain_point_analysis = _text(output.get("pain_point_analysis"))
            result.supply_chain_analysis = _text(output.get("supply_chain_analysis"))
        gaps = output.get("evidence_gaps", [])
        if isinstance(gaps, list):
            result.evidence_gaps.extend(str(item)[:240] for item in gaps[:5] if item)
    result.evidence_gaps = list(dict.fromkeys(result.evidence_gaps))[:12]


def _finish_result(result: AgentResult, started: float, *, accumulate: bool = False) -> None:
    elapsed = round((time.perf_counter() - started) * 1000)
    result.duration_ms = result.duration_ms + elapsed if accumulate else elapsed
    result.finished_at = utc_now_iso()
    result.input_tokens = sum(step.input_tokens for step in result.steps)
    result.output_tokens = sum(step.output_tokens for step in result.steps)
    result.estimated_cost_usd = _estimated_cost(
        result.input_tokens,
        result.output_tokens,
        result.provider_config,
    )


def _would_exceed_budget(
    result: AgentResult,
    config: LlmProviderConfig | None,
    prompt: str,
    max_tokens: int,
) -> bool:
    if config is None or config.max_run_cost_usd is None:
        return False
    if config.input_usd_per_million is None or config.output_usd_per_million is None:
        return False
    spent = _estimated_cost(
        sum(step.input_tokens for step in result.steps),
        sum(step.output_tokens for step in result.steps),
        config,
    ) or 0.0
    next_cost = _estimated_stage_cost(config, prompt, max_tokens)
    return spent + next_cost > config.max_run_cost_usd


def _estimated_stage_cost(config: LlmProviderConfig, prompt: str, max_tokens: int) -> float:
    if config.input_usd_per_million is None or config.output_usd_per_million is None:
        return 0.0
    input_tokens = _rough_token_count(prompt) + _rough_token_count(_system_instruction())
    return round(
        (
            input_tokens * config.input_usd_per_million
            + max_tokens * config.output_usd_per_million
        )
        / 1_000_000,
        6,
    )


def _rough_token_count(text: str) -> int:
    return max(1, int(len(text) / 3.5))


def _budget_skipped_step(name: str, label: str, config: LlmProviderConfig | None) -> AgentStep:
    budget = config.max_run_cost_usd if config else None
    reason = (
        f"AI 单次预算 ${budget:.4f} 不足，已跳过该阶段并使用规则降级。"
        if isinstance(budget, (int, float))
        else "AI 单次预算不足，已跳过该阶段并使用规则降级。"
    )
    return _skipped_step(name, label, reason)


def _is_budget_skip(step: AgentStep) -> bool:
    return step.status == "skipped" and "AI 单次预算" in (step.error or "")


def _run_stage(
    config: LlmProviderConfig | None,
    name: str,
    label: str,
    prompt: str,
    required_fields: set[str],
    max_tokens: int,
) -> AgentStep:
    started_at = utc_now_iso()
    started = time.perf_counter()
    last_error: Exception | None = None
    if config is None:
        return _skipped_step(name, label, "LLM provider credentials are not configured.")
    for attempt in range(3):
        try:
            response = _call_provider(config, prompt, max_tokens)
            output = _extract_json(response.text)
            missing = [field for field in required_fields if field not in output]
            if missing:
                raise ValueError(f"missing fields: {', '.join(sorted(missing))}")
            return AgentStep(
                name=name,
                label=label,
                status="completed",
                started_at=started_at,
                finished_at=utc_now_iso(),
                duration_ms=round((time.perf_counter() - started) * 1000),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                request_id=response.request_id,
                output=_bounded_output(output),
            )
        except Exception as exc:
            last_error = exc
            if attempt >= 2 or not _retryable_provider_error(exc):
                break
            retry_after = _retry_after_seconds(exc)
            time.sleep(retry_after if retry_after is not None else 1.5 * (attempt + 1))
    return AgentStep(
        name=name,
        label=label,
        status="failed",
        started_at=started_at,
        finished_at=utc_now_iso(),
        duration_ms=round((time.perf_counter() - started) * 1000),
        error=str(last_error)[:400] if last_error else "unknown provider error",
    )


def _retryable_provider_error(exc: Exception) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code in {429, 500, 502, 503, 529}


def _retry_after_seconds(exc: Exception) -> float | None:
    if not isinstance(exc, urllib.error.HTTPError):
        return None
    raw = exc.headers.get("retry-after") if exc.headers else None
    try:
        return max(0.5, min(15.0, float(raw))) if raw else None
    except ValueError:
        return None


def _skipped_step(name: str, label: str, reason: str) -> AgentStep:
    timestamp = utc_now_iso()
    return AgentStep(
        name=name,
        label=label,
        status="skipped",
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=0,
        error=reason,
    )


def test_llm_connection() -> dict[str, Any]:
    config = resolve_llm_config()
    if config is None:
        return {
            "ok": False,
            "status": "missing_credentials",
            "error": "AI API 尚未配置",
        }
    started = time.perf_counter()
    try:
        response = _call_provider(
            config,
            'Return only this JSON object: {"ok": true}',
            64,
        )
        return {
            "ok": True,
            "status": "connected",
            "provider": config.provider,
            "protocol": config.protocol,
            "provider_label": config.label,
            "model": config.model,
            "source": config.source,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "request_id": response.request_id,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "provider_error",
            "provider": config.provider,
            "protocol": config.protocol,
            "provider_label": config.label,
            "model": config.model,
            "source": config.source,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc)[:400],
        }


def _call_provider(config: LlmProviderConfig, prompt: str, max_tokens: int) -> ProviderResponse:
    if config.protocol == "openai":
        return _call_openai(config, prompt, max_tokens)
    if config.protocol == "anthropic":
        return _call_anthropic(config, prompt, max_tokens)
    raise RuntimeError(f"Unsupported provider protocol {config.protocol}")


def _call_openai(config: LlmProviderConfig, prompt: str, max_tokens: int) -> ProviderResponse:
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": _system_instruction()},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    if config.provider != "gemini":
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=llm_timeout_seconds(), context=SSL_CONTEXT) as response:
            data = json.loads(response.read().decode("utf-8"))
            request_id = response.headers.get("x-request-id")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_provider_http_error(exc)) from exc
    usage = data.get("usage", {})
    return ProviderResponse(
        text=str(data["choices"][0]["message"]["content"]),
        input_tokens=int(usage.get("prompt_tokens", 0) or 0),
        output_tokens=int(usage.get("completion_tokens", 0) or 0),
        request_id=request_id or data.get("id"),
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def _call_anthropic(config: LlmProviderConfig, prompt: str, max_tokens: int) -> ProviderResponse:
    payload = {
        "model": config.model,
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "system": _system_instruction(),
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        f"{config.base_url}/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=llm_timeout_seconds(), context=SSL_CONTEXT) as response:
            data = json.loads(response.read().decode("utf-8"))
            request_id = response.headers.get("request-id")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_provider_http_error(exc)) from exc
    parts = data.get("content", [])
    usage = data.get("usage", {})
    return ProviderResponse(
        text="\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)),
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        request_id=request_id or data.get("id"),
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def _provider_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    details = body[:300] if body else exc.reason
    return f"HTTP {exc.code}: {details}"


def _system_instruction() -> str:
    return (
        "You are one specialist in the OpportunityOS product intelligence workflow. "
        "Use only the supplied real-source evidence. Never invent patents, suppliers, products, prices, reviews, "
        "market sizes, or citations. Explicitly identify missing evidence. Return concise Chinese analysis as strict JSON."
    )


def _trend_market_prompt(context: dict[str, Any]) -> str:
    payload = {"keyword": context.get("keyword"), "trend": context.get("trend")}
    return _json_prompt(
        "你是 Trend Analysis Agent 与 Market Analysis Agent。分析需求信号、增长、相关词与主要市场。",
        {
            "market_analysis": "string",
            "trend_analysis": "string",
            "trend_judgement": "growing|stable|declining|low_confidence",
            "evidence_gaps": ["string"],
        },
        payload,
    )


def _patent_prompt(context: dict[str, Any]) -> str:
    payload = {"keyword": context.get("keyword"), "patents": context.get("patents", [])}
    return _json_prompt(
        "你是 Patent Analysis Agent。总结法律状态、核心技术方向、风险与可参考方向；必须声明不构成法律意见。",
        {
            "patent_analysis": "string",
            "risk_level": "low|medium|high|unknown",
            "core_technical_directions": ["string"],
            "reference_directions": ["string"],
            "evidence_gaps": ["string"],
        },
        payload,
    )


def _commercial_prompt(context: dict[str, Any]) -> str:
    payload = {
        "keyword": context.get("keyword"),
        "competitors": context.get("competitors", []),
        "pain_points": context.get("pain_points", []),
        "suppliers": context.get("suppliers", []),
    }
    return _json_prompt(
        "你同时承担 Competitor、Pain Point 与 Supply Chain Agent。分别输出竞品、痛点和供应链分析。",
        {
            "competitor_analysis": "string",
            "pain_point_analysis": "string",
            "supply_chain_analysis": "string",
            "evidence_gaps": ["string"],
        },
        payload,
    )


def _innovation_prompt(context: dict[str, Any], result: AgentResult) -> str:
    payload = {
        "keyword": context.get("keyword"),
        "evidence": _compact_context(context),
        "specialist_analysis": {
            "market": result.market_analysis,
            "trend": result.trend_analysis,
            "patent": result.patent_analysis,
            "competitor": result.competitor_analysis,
            "pain": result.pain_point_analysis,
            "supply": result.supply_chain_analysis,
        },
    }
    return _json_prompt(
        "你是 Innovation Agent。创新必须能追溯到输入证据；证据不足时减少数量，不得凑数。",
        {
            "innovation_analysis": "string",
            "ideas": [
                {
                    "title": "string",
                    "description": "string",
                    "market_value_score": "0-100",
                    "difficulty_score": "0-100",
                    "cost_impact": "low|medium|high",
                    "differentiation_score": "0-100",
                    "target_user": "string",
                    "suggested_features": ["string"],
                }
            ],
        },
        payload,
        extra="ideas 最多 6 条。",
    )


def _report_prompt(
    context: dict[str, Any],
    result: AgentResult,
    scores: dict[str, int | str],
    ideas: list[dict[str, Any]],
) -> str:
    payload = {
        "keyword": context.get("keyword"),
        "weighted_scores": scores,
        "specialist_analysis": {
            "market": result.market_analysis,
            "trend": result.trend_analysis,
            "patent": result.patent_analysis,
            "competitor": result.competitor_analysis,
            "pain": result.pain_point_analysis,
            "supply": result.supply_chain_analysis,
            "innovation": result.innovation_analysis,
        },
        "ideas": ideas[:6],
        "evidence_gaps": result.evidence_gaps,
    }
    return _json_prompt(
        "你是 Scoring Agent 与 Report Agent。解释给定的确定性加权评分，不得自行改分；生成最终执行摘要与决策建议。",
        {
            "executive_summary": "string",
            "score_reasoning": "string",
            "final_recommendation": "string",
            "risk_notice": "string",
        },
        payload,
        extra="必须说明不构成法律或投资建议，并针对证据缺口给出下一步验证动作。",
    )


def _json_prompt(
    role: str,
    schema: dict[str, Any],
    evidence: dict[str, Any],
    *,
    extra: str = "",
) -> str:
    serialized = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))[:16000]
    return (
        f"{role}\n只返回 JSON，不要 Markdown。\n"
        f"JSON schema: {json.dumps(schema, ensure_ascii=False)}\n"
        f"{extra}\n真实证据：{serialized}"
    )


def _compact_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "trend": context.get("trend"),
        "patents": list(context.get("patents", []))[:5],
        "competitors": list(context.get("competitors", []))[:5],
        "pain_points": list(context.get("pain_points", []))[:5],
        "suppliers": list(context.get("suppliers", []))[:6],
    }


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("agent response must be a JSON object")
    return payload


def _bounded_output(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) <= 12000:
        return payload
    return {"truncated": True, "preview": serialized[:12000]}


def _ideas_from_payload(data: dict[str, Any]) -> list[AgentIdea]:
    ideas = []
    for item in data.get("ideas", [])[:6]:
        if not isinstance(item, dict):
            continue
        ideas.append(
            AgentIdea(
                title=str(item.get("title") or "AI opportunity idea")[:120],
                description=str(item.get("description") or "")[:800],
                market_value_score=_score(item.get("market_value_score"), 70),
                difficulty_score=_score(item.get("difficulty_score"), 50),
                cost_impact=_cost(item.get("cost_impact")),
                differentiation_score=_score(item.get("differentiation_score"), 70),
                target_user=str(item.get("target_user") or "validated buyers")[:120],
                suggested_features=[str(feature)[:120] for feature in item.get("suggested_features", [])[:5] if feature],
            )
        )
    return ideas


def _estimated_cost(
    input_tokens: int,
    output_tokens: int,
    config: LlmProviderConfig | None,
) -> float | None:
    if (
        config is None
        or config.input_usd_per_million is None
        or config.output_usd_per_million is None
    ):
        return None
    return round(
        (
            input_tokens * config.input_usd_per_million
            + output_tokens * config.output_usd_per_million
        )
        / 1_000_000,
        6,
    )


def _empty_result(
    mode: str,
    provider: str | None,
    model: str | None,
    status: str,
    error: str | None,
    started_at: str,
    started: float,
) -> AgentResult:
    result = AgentResult(
        run_id=str(uuid4()),
        mode=mode,
        provider=provider,
        model=model,
        status=status,
        error=error,
        started_at=started_at,
    )
    result.steps = [
        AgentStep(
            name=name,
            label=label,
            status="skipped",
            started_at=started_at,
            finished_at=utc_now_iso(),
            duration_ms=0,
            error="LLM provider credentials are not configured.",
        )
        for name, label in [
            ("trend_market", "趋势与市场 Agent"),
            ("patent_risk", "专利风险 Agent"),
            ("commercial_evidence", "竞品、痛点与供应链 Agent"),
            ("innovation", "创新方向 Agent"),
            ("scoring_report", "评分与报告 Agent"),
        ]
    ]
    _finish_result(result, started)
    return result


def _score(value: Any, fallback: int) -> int:
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return fallback


def _cost(value: Any) -> str:
    text = str(value or "medium").lower()
    return text if text in {"low", "medium", "high"} else "medium"


def _text(value: Any) -> str | None:
    if not value:
        return None
    return str(value).strip()[:2000]
