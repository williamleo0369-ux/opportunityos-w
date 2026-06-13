from __future__ import annotations

from typing import Any

from app.schemas import Competitor, InnovationIdea, PainPoint, Patent, SupplyChainItem, TrendData


def _source_status(count: int, *, guarded: bool = False) -> str:
    if count > 0:
        return "ok"
    return "guarded" if guarded else "empty"


def _platform_count(rows: list[SupplyChainItem], platform: str) -> int:
    return sum(1 for item in rows if platform.lower() in item.platform.lower())


def build_data_quality(
    *,
    trend_rows: list[TrendData],
    patents: list[Patent],
    competitors: list[Competitor],
    pain_points: list[PainPoint],
    supply_chain: list[SupplyChainItem],
    innovation_ideas: list[InnovationIdea],
    agent_result: Any | None = None,
) -> dict[str, Any]:
    trend = trend_rows[0] if trend_rows else None
    trend_raw = trend.raw_data if trend else {}
    google_suggest_count = len(trend_raw.get("google_suggest", [])) if isinstance(trend_raw.get("google_suggest"), list) else 0
    amazon_suggest_count = len(trend_raw.get("amazon_suggest", [])) if isinstance(trend_raw.get("amazon_suggest"), list) else 0
    wiki = trend_raw.get("wikimedia", {}) if isinstance(trend_raw.get("wikimedia"), dict) else {}
    wiki_count = len(wiki.get("pageviews", [])) if isinstance(wiki.get("pageviews"), list) else int(wiki.get("totalhits", 0) or 0)

    amazon_review_clusters = sum(1 for item in pain_points if item.source == "amazon_product_page_reviews")
    reddit_clusters = sum(1 for item in pain_points if item.source == "reddit_search_rss")
    derived_pain_clusters = sum(1 for item in pain_points if item.source not in {"amazon_product_page_reviews", "reddit_search_rss", "real_source_gap"})
    real_gap_clusters = sum(1 for item in pain_points if item.source == "real_source_gap")
    alibaba_count = _platform_count(supply_chain, "alibaba")
    count_1688 = _platform_count(supply_chain, "1688")
    ec21_count = _platform_count(supply_chain, "ec21")

    if isinstance(agent_result, dict):
        agent_status = agent_result.get("status")
        agent_provider = agent_result.get("provider")
        agent_model = agent_result.get("model")
        agent_steps = agent_result.get("steps", [])
    else:
        agent_status = getattr(agent_result, "status", None) if agent_result else None
        agent_provider = getattr(agent_result, "provider", None) if agent_result else None
        agent_model = getattr(agent_result, "model", None) if agent_result else None
        agent_steps = getattr(agent_result, "steps", []) if agent_result else []
    agent_available = agent_status in {
        "completed",
        "completed_with_gaps",
        "analysis_completed",
        "analysis_completed_with_gaps",
    }
    completed_agent_steps = sum(
        1
        for step in agent_steps
        if (step.get("status") if isinstance(step, dict) else getattr(step, "status", None)) == "completed"
    )

    sources = [
        {
            "key": "google_suggest",
            "label": "Google Suggest",
            "category": "趋势/需求",
            "status": _source_status(google_suggest_count),
            "count": google_suggest_count,
            "note": "关键词扩展与需求强度信号",
        },
        {
            "key": "amazon_suggest",
            "label": "Amazon Suggest",
            "category": "趋势/需求",
            "status": _source_status(amazon_suggest_count),
            "count": amazon_suggest_count,
            "note": "电商搜索意图与长尾词信号",
        },
        {
            "key": "wikimedia",
            "label": "Wikimedia",
            "category": "趋势/需求",
            "status": _source_status(wiki_count),
            "count": wiki_count,
            "note": "公开搜索与页面浏览补充信号",
        },
        {
            "key": "google_patents",
            "label": "Google Patents",
            "category": "专利",
            "status": _source_status(len(patents)),
            "count": len(patents),
            "note": "相关专利引用与法律状态估算",
        },
        {
            "key": "amazon_search",
            "label": "Amazon Search HTML",
            "category": "竞品",
            "status": _source_status(len(competitors)),
            "count": len(competitors),
            "note": "真实搜索结果中的价格、评分和评论量",
        },
        {
            "key": "amazon_reviews",
            "label": "Amazon Product Reviews",
            "category": "用户痛点",
            "status": _source_status(amazon_review_clusters),
            "count": amazon_review_clusters,
            "note": "商品页评论可解析时提取差评痛点",
        },
        {
            "key": "reddit",
            "label": "Reddit RSS",
            "category": "用户痛点",
            "status": _source_status(reddit_clusters),
            "count": reddit_clusters,
            "note": "公开讨论中的问题与需求表达",
        },
        {
            "key": "alibaba",
            "label": "Alibaba.com",
            "category": "供应链",
            "status": _source_status(alibaba_count),
            "count": alibaba_count,
            "note": "B2B 供应商、MOQ 和报价信号",
        },
        {
            "key": "1688",
            "label": "1688",
            "category": "供应链",
            "status": _source_status(count_1688, guarded=True),
            "count": count_1688,
            "note": "需要有效会话 Cookie；无会话时不生成模拟数据",
        },
        {
            "key": "ec21",
            "label": "EC21",
            "category": "供应链",
            "status": _source_status(ec21_count),
            "count": ec21_count,
            "note": "B2B 供应商与产地补充信号",
        },
        {
            "key": "llm_agent",
            "label": "LLM Agent",
            "category": "分析编排",
            "status": "ok" if agent_available else agent_status or "not_recorded",
            "count": completed_agent_steps if agent_available else 0,
            "note": f"{agent_provider}/{agent_model} · {completed_agent_steps}/5 stages" if agent_available else "未配置、超时或旧报告未记录时使用规则降级",
        },
    ]

    category_scores = {
        "trend": 20 if trend and (google_suggest_count or amazon_suggest_count or wiki_count) else 0,
        "patent": 15 if patents else 0,
        "competitor": 20 if competitors else 0,
        "pain": 15 if amazon_review_clusters or reddit_clusters or derived_pain_clusters else 0,
        "supply": 20 if supply_chain else 0,
        "innovation": 10 if innovation_ideas and not any("真实证据补全验证包" in item.idea_title for item in innovation_ideas) else 3 if innovation_ideas else 0,
    }
    confidence_score = min(100, sum(category_scores.values()))
    confidence_level = "high" if confidence_score >= 75 else "medium" if confidence_score >= 50 else "low"

    gaps: list[str] = []
    if not competitors:
        gaps.append("Amazon 结构化竞品本次未返回，价格与竞争评分置信度下降。")
    if not patents:
        gaps.append("Google Patents 本次未返回引用，专利风险需要补采或人工复核。")
    if not supply_chain:
        gaps.append("B2B 供应商本次未返回可靠行，供应链与利润测算为低置信。")
    if not amazon_review_clusters and not reddit_clusters:
        gaps.append("真实评论/社区痛点不足，痛点部分更多依赖 listing、专利和搜索词信号。")
    if count_1688 == 0:
        gaps.append("1688 需要有效会话 Cookie；当前未使用 1688 数据，也未生成模拟供应商。")
    if real_gap_clusters:
        gaps.append("存在真实来源缺口提示，建议补采评论、竞品或供应商后再做高成本决策。")
    if not agent_available:
        gaps.append("LLM Agent 未完成或未记录，本次分析使用真实证据规则降级输出。")
    elif agent_status in {"completed_with_gaps", "analysis_completed_with_gaps"}:
        gaps.append("部分 Agent 阶段失败，已保留成功阶段并对缺失分析使用规则降级。")
    agent_evidence_gaps = (
        agent_result.get("evidence_gaps", [])
        if isinstance(agent_result, dict)
        else getattr(agent_result, "evidence_gaps", [])
        if agent_result
        else []
    )
    gaps.extend(f"Agent 证据缺口：{item}" for item in agent_evidence_gaps[:5] if item)

    return {
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "category_scores": category_scores,
        "evidence_counts": {
            "trend_rows": len(trend_rows),
            "patents": len(patents),
            "competitors": len(competitors),
            "pain_points": len(pain_points),
            "suppliers": len(supply_chain),
            "innovation_ideas": len(innovation_ideas),
        },
        "sources": sources,
        "gaps": gaps,
        "limitations": [
            "公开网页来源可能受反爬、地区、登录态和页面结构变化影响。",
            "专利状态为商业情报估算，不构成法律意见。",
            "价格、MOQ 和评论量来自采集时点，需要在采购或投放前复核。",
        ],
    }


def data_quality_markdown(data_quality: dict[str, Any]) -> str:
    sources = data_quality.get("sources", [])
    gaps = data_quality.get("gaps", [])
    source_lines = [
        f"- {item.get('label')}: {item.get('status')} / {item.get('count')} signals. {item.get('note')}"
        for item in sources
    ]
    gap_lines = [f"- {item}" for item in gaps] or ["- No major source gap was detected from the collected evidence."]
    return "\n".join(
        [
            f"Confidence score: {data_quality.get('confidence_score', 0)}/100 ({data_quality.get('confidence_level', 'low')}).",
            "",
            "Source coverage:",
            *source_lines,
            "",
            "Known gaps:",
            *gap_lines,
        ]
    )
