from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from app.schemas import (
    Competitor,
    InnovationIdea,
    Opportunity,
    PainPoint,
    Patent,
    Report,
    SearchRequest,
    SearchTask,
    SupplyChainItem,
    TrendData,
)
from app.services.ai_agent import AgentResult, finalize_opportunity_agent, run_opportunity_analysis, skipped_agent_result
from app.services.data_quality import build_data_quality, data_quality_markdown
from app.services.database_store import load_user_payload, user_usage
from app.services.real_sources import (
    collect_1688_supply_chain,
    collect_amazon_competitors,
    collect_amazon_product_reviews,
    collect_alibaba_supply_chain,
    collect_ec21_supply_chain,
    collect_google_patents,
    collect_reddit_pain_posts,
    collect_trend_signal,
    ReviewSignal,
)
from app.services.source_credentials import CredentialDecryptionError, load_1688_cookie


def now() -> datetime:
    return datetime.now(timezone.utc)


def _payload_float(value: object) -> float | None:
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _ai_agent_budget_status(user_id: str) -> tuple[bool, str | None]:
    payload = load_user_payload(user_id)
    quota = _payload_float(payload.get("ai_cost_quota_monthly")) if payload else None
    if quota is None:
        return True, None
    usage = user_usage(user_id)
    used = max(0.0, float(usage.get("ai_cost_this_month_usd") or 0))
    if used >= quota:
        return (
            False,
            f"本月 AI 成本额度已用完（已用 ${used:.4f} / 额度 ${quota:.4f}）。本次报告已跳过 AI Agent，改用真实证据与规则分析。",
        )
    return True, None


def expand_keywords(keyword: str) -> list[str]:
    base = keyword.strip()
    normalized = base.lower()
    if any("\u4e00" <= char <= "\u9fff" for char in base):
        translated = {
            "宠物饮水机": "pet water fountain",
            "露营灯": "camping lantern",
            "厨房切菜器": "kitchen slicer",
            "折叠收纳箱": "foldable storage box",
            "便携风扇": "portable fan",
            "温奶器": "baby bottle warmer",
            "桌面收纳": "desk organizer",
            "清洁刷": "cleaning brush",
            "狗牵引绳": "dog leash",
            "猫砂盆": "cat litter box",
        }.get(base, f"smart {base} product")
    else:
        translated = normalized

    return [
        translated,
        f"smart {translated}",
        f"portable {translated}",
        f"quiet {translated}",
        f"premium {translated}",
        f"{translated} replacement parts",
    ]


def generate_trend_data(opportunity_id: str, keyword: str, target_market: str, related: list[str]) -> TrendData:
    signal = collect_trend_signal(keyword, target_market)
    merged_related = []
    for item in [*signal.related_keywords, *related]:
        if item and item not in merged_related:
            merged_related.append(item)
    return TrendData(
        id=str(uuid4()),
        opportunity_id=opportunity_id,
        keyword=signal.keyword,
        source=signal.source,
        country=target_market,
        time_period="12 months",
        growth_rate=signal.growth_rate,
        trend_score=signal.trend_score,
        monthly_search_volume=signal.monthly_search_volume,
        related_keywords=merged_related[:12],
        country_distribution=signal.country_distribution,
        monthly_data=signal.monthly_data,
        raw_data=signal.raw_data,
        created_at=now(),
    )


def generate_patents(opportunity_id: str, keyword: str) -> list[Patent]:
    patents: list[Patent] = []
    for signal in collect_google_patents(keyword, limit=12):
        patents.append(
            Patent(
                id=str(uuid4()),
                opportunity_id=opportunity_id,
                patent_title=signal.title,
                patent_number=signal.number,
                country=signal.country,
                applicant=signal.applicant,
                inventor=signal.inventor,
                filing_date=signal.filing_date,
                publication_date=signal.publication_date,
                grant_date=signal.grant_date,
                estimated_expiry_date=signal.estimated_expiry_date,
                legal_status=signal.legal_status,
                risk_level=signal.risk_level,
                abstract=signal.abstract,
                claims=signal.claims,
                original_url=signal.original_url,
                raw_data=signal.raw_data,
                created_at=now(),
                updated_at=now(),
            )
        )
    return patents


def generate_competitors(opportunity_id: str, keyword: str) -> list[Competitor]:
    competitors: list[Competitor] = []
    for signal in collect_amazon_competitors(keyword, limit=6):
        competitors.append(
            Competitor(
                id=str(uuid4()),
                opportunity_id=opportunity_id,
                product_title=signal.title,
                platform=signal.platform,
                brand=signal.brand,
                price=signal.price,
                currency=signal.currency,
                rating=signal.rating,
                review_count=signal.review_count,
                estimated_sales=signal.estimated_sales,
                product_url=signal.product_url,
                image_url=signal.image_url,
                main_features=signal.main_features,
                weaknesses=signal.weaknesses,
                raw_data=signal.raw_data,
                created_at=now(),
            )
        )
    return competitors


def generate_pain_points(
    opportunity_id: str,
    keyword: str,
    patents: list[Patent],
    competitors: list[Competitor],
    related: list[str],
    reviews: list[ReviewSignal],
) -> list[PainPoint]:
    signals: list[tuple[str, int, str, list[str], list[str]]] = []
    buckets = [
        ("清洁维护复杂度高", ["hard to clean", "difficult to clean", "gunk", "bacteria", "slime", "mold", "filter replacement", "dirty"], {}),
        ("内部材料和饮水安全不透明", ["unsafe", "safety", "plastic smell", "bpa", "foam", "chemical", "electrocution", "rust"], {}),
        ("泵体噪音、寿命和可替换性是关键风险", ["pump broke", "pump stopped", "noise", "noisy", "loud", "replacement pump", "stopped working"], {}),
        ("购买后不确定宠物是否真的使用", ["not interested", "won't use", "would not use", "doesn't use", "prefer bowl", "took a day", "took a week"], {}),
        ("价格与高质量方案之间存在落差", ["expensive", "cheaply made", "not worth", "waste of money", "overpriced", "scam"], {}),
    ]
    amazon_problem_terms = [
        word
        for _, keywords, _ in buckets
        for word in keywords
    ]
    for review in reviews:
        combined = f"{review.title}. {review.body}"
        lower = combined.lower()
        rating_text = str(review.raw_data.get("rating", ""))
        rating_match = re.search(r"([1-5](?:\.\d+)?)", rating_text)
        rating = float(rating_match.group(1)) if rating_match else 0.0
        if review.source == "amazon_product_page_reviews" and rating >= 4 and not any(term in lower for term in amazon_problem_terms):
            continue
        for _, keywords, source_examples in buckets:
            if any(word in lower for word in keywords):
                source_examples.setdefault(review.source, []).append((combined[:360], review.url))

    for point, _, source_examples in buckets:
        for source, evidence in source_examples.items():
            if evidence:
                examples = [item[0] for item in evidence]
                urls = [item[1] for item in evidence if item[1]]
                source_weight = 16 if source == "amazon_product_page_reviews" else 12
                signals.append((point, min(95, 45 + len(examples) * source_weight), source, examples, urls))

    lower_titles = " ".join(item.product_title.lower() for item in competitors)
    lower_patents = " ".join(item.abstract.lower() for item in patents)
    if "filter" in lower_titles or "filter" in lower_patents:
        signals.append(
            (
                "过滤耗材与替换频率需要更清晰",
                62,
                "patent_and_listing_signals",
                [item.abstract for item in patents[:2] if item.abstract],
                [item.original_url for item in patents[:2] if item.original_url],
            )
        )
    if "stainless" in lower_titles or "steel" in lower_titles:
        signals.append(
            (
                "材质升级是明显差异化入口",
                58,
                "amazon_listing_signals",
                [item.product_title for item in competitors[:2]],
                [item.product_url for item in competitors[:2] if item.product_url],
            )
        )
    if "pump" in " ".join(related).lower() or "pump" in lower_patents:
        signals.append(
            (
                "泵体噪音、寿命和可替换性是关键风险",
                56,
                "suggest_and_patent_signals",
                related[:2],
                [item.original_url for item in patents[:2] if item.original_url],
            )
        )
    if "clean" in lower_titles or "clean" in lower_patents:
        signals.append(
            (
                "清洁维护复杂度会影响复购与差评",
                54,
                "patent_and_listing_signals",
                [item.abstract for item in patents[:2] if item.abstract],
                [item.original_url for item in patents[:2] if item.original_url],
            )
        )
    if not signals:
        signals.append(("真实评论源暂未返回结果，先依据专利摘要和搜索相关词识别验证问题", 35, "real_source_gap", related[:2], []))

    deduped: list[tuple[str, int, str, list[str], list[str]]] = []
    seen: set[str] = set()
    for point, frequency, source, examples, urls in sorted(signals, key=lambda item: item[1], reverse=True):
        if point in seen:
            continue
        seen.add(point)
        deduped.append((point, frequency, source, examples, list(dict.fromkeys(urls))))

    return [
        PainPoint(
            id=str(uuid4()),
            opportunity_id=opportunity_id,
            pain_point=point,
            frequency=frequency,
            sentiment="negative",
            source=source,
            example_reviews=examples[:2],
            evidence_urls=urls[:3],
            ai_summary=f"基于 {source_display_name(source)} 等真实信号，{keyword} 的验证重点是：{point}。",
            created_at=now(),
        )
        for point, frequency, source, examples, urls in deduped[:6]
    ]


def source_display_name(source: str) -> str:
    labels = {
        "amazon_product_page_reviews": "Amazon 商品页评论",
        "reddit_search_rss": "Reddit 公开讨论",
        "patent_and_listing_signals": "专利与 listing",
        "amazon_listing_signals": "Amazon listing",
        "suggest_and_patent_signals": "搜索建议与专利",
        "real_source_gap": "低置信真实来源",
    }
    return labels.get(source, source)


def generate_supply_chain(
    opportunity_id: str,
    keyword: str,
    *,
    user_id: str,
) -> list[SupplyChainItem]:
    supply_rows: list[SupplyChainItem] = []
    seen: set[tuple[str, str]] = set()
    try:
        cookie_1688 = load_1688_cookie(user_id)
    except CredentialDecryptionError:
        cookie_1688 = ""
    signals = [
        *collect_1688_supply_chain(keyword, limit=4, cookie=cookie_1688 or None),
        *collect_alibaba_supply_chain(keyword, limit=6),
        *collect_ec21_supply_chain(keyword, limit=6),
    ]
    for signal in signals:
        key = (signal.supplier_name.lower(), signal.product_title.lower()[:80])
        if key in seen:
            continue
        seen.add(key)
        supply_rows.append(
            SupplyChainItem(
                id=str(uuid4()),
                opportunity_id=opportunity_id,
                supplier_name=signal.supplier_name,
                platform=signal.platform,
                product_title=signal.product_title,
                unit_price_min=signal.unit_price_min,
                unit_price_max=signal.unit_price_max,
                moq=signal.moq,
                location=signal.location,
                supplier_url=signal.supplier_url,
                production_maturity_score=signal.production_maturity_score,
                logistics_note=signal.logistics_note,
                raw_data=signal.raw_data,
                created_at=now(),
            )
        )
        if len(supply_rows) >= 10:
            break
    return supply_rows


def generate_innovation_ideas(
    opportunity_id: str,
    keyword: str,
    pain_points: list[PainPoint] | None = None,
    patents: list[Patent] | None = None,
    competitors: list[Competitor] | None = None,
    supply_chain: list[SupplyChainItem] | None = None,
    agent_result: AgentResult | None = None,
) -> list[InnovationIdea]:
    if agent_result and agent_result.ideas:
        return [
            InnovationIdea(
                id=str(uuid4()),
                opportunity_id=opportunity_id,
                idea_title=idea.title,
                idea_description=idea.description,
                market_value_score=idea.market_value_score,
                difficulty_score=idea.difficulty_score,
                cost_impact=idea.cost_impact,
                differentiation_score=idea.differentiation_score,
                target_user=idea.target_user,
                suggested_features=idea.suggested_features or ["validate with real buyers", "show proof in listing", "define manufacturable spec"],
                created_at=now(),
            )
            for idea in agent_result.ideas[:6]
        ]
    pain_points = pain_points or []
    patents = patents or []
    competitors = competitors or []
    supply_chain = supply_chain or []
    corpus = " ".join(
        [
            *[item.pain_point for item in pain_points],
            *[example for item in pain_points for example in item.example_reviews],
            *[item.abstract for item in patents],
            *[item.product_title for item in competitors],
            *[weakness for item in competitors for weakness in item.weaknesses],
            *[item.product_title for item in supply_chain],
        ],
    ).lower()
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()

    def add_candidate(
        key: str,
        title: str,
        description: str,
        evidence: str,
        market_value: int,
        difficulty: int,
        cost: str,
        differentiation: int,
        target_user: str,
        features: list[str],
    ) -> None:
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "title": title,
                "description": f"{description} 证据来源：{evidence}。",
                "market_value": market_value,
                "difficulty": difficulty,
                "cost": cost,
                "differentiation": differentiation,
                "target_user": target_user,
                "features": features,
            }
        )

    top_pain = pain_points[0] if pain_points else None
    if any(term in corpus for term in ["clean", "cleaning", "filter", "slime", "mold", "清洁", "过滤", "滤芯"]):
        evidence = source_display_name(top_pain.source) if top_pain else "专利/Listing 文本"
        add_candidate(
            "cleaning",
            "证据驱动的快拆清洁结构",
            f"围绕 {keyword} 的清洁、过滤或维护信号，优先验证少零件、免工具拆洗和滤芯可视化。",
            evidence,
            78,
            46,
            "medium",
            82,
            "重视维护成本的家庭用户",
            ["免工具拆洗", "滤芯寿命可视化", "可冲洗内腔结构"],
        )
    if any(term in corpus for term in ["pump", "noise", "noisy", "loud", "quiet", "噪音", "静音", "泵"]):
        evidence = source_display_name(top_pain.source) if top_pain else "搜索建议/专利文本"
        add_candidate(
            "quiet_pump",
            "低噪可替换核心组件",
            f"围绕 {keyword} 的噪音、寿命或替换信号，验证可单独更换的低噪组件，而不是整机报废。",
            evidence,
            74,
            52,
            "medium",
            79,
            "夜间使用和小户型用户",
            ["低噪组件", "备件独立销售", "故障提示"],
        )
    if any(term in corpus for term in ["stainless", "steel", "safe", "bpa", "rust", "material", "材质", "安全", "不锈钢"]):
        evidence = "Amazon Listing/评论文本" if competitors or pain_points else "专利摘要"
        add_candidate(
            "material_safety",
            "材料安全可证明版本",
            f"围绕 {keyword} 的材料、安全或耐用信号，优先把材质证明、接触面材料和清洁方式做成可被买家看懂的卖点。",
            evidence,
            72,
            44,
            "medium",
            76,
            "愿意为安全感付费的买家",
            ["材质证书展示", "接触面升级", "耐腐蚀说明"],
        )
    if any(item.risk_level == "high" or item.legal_status == "active" for item in patents):
        add_candidate(
            "patent_boundary",
            "专利边界优先的结构验证",
            f"{keyword} 已返回活跃或高风险专利引用，首轮样品不应只追求外观差异，而要围绕结构路径和 claims 边界做验证。",
            "Google Patents",
            68,
            58,
            "medium",
            72,
            "需要降低侵权不确定性的卖家",
            ["claims 对照表", "替代结构方案", "律师复核清单"],
        )
    low_moq = [item for item in supply_chain if 0 < item.moq <= 200]
    priced_suppliers = [item for item in supply_chain if item.unit_price_min > 0 or item.unit_price_max > 0]
    if low_moq or priced_suppliers:
        evidence_platforms = ", ".join(sorted({item.platform for item in [*low_moq, *priced_suppliers]}))
        add_candidate(
            "supplier_validation",
            "小批量报价验证 SKU",
            f"{keyword} 已有可用 B2B 供应商信号，先用最低可行规格做小批量报价和样品一致性验证。",
            evidence_platforms,
            70,
            38,
            "low",
            68,
            "跨境测试卖家",
            ["小批量 MOQ 对比", "样品一致性表", "报价有效期记录"],
        )
    if competitors:
        add_candidate(
            "listing_proof",
            "竞品弱点可视化 Listing",
            f"Amazon 结构化 listing 已返回竞品信号，首轮页面应把真实痛点、材料或维护差异做成图片证据，而不是泛化宣传。",
            "Amazon Search HTML",
            66,
            32,
            "low",
            70,
            "先看评价再下单的买家",
            ["痛点对比图", "维护步骤图", "规格证据区"],
        )
    if not candidates:
        add_candidate(
            "evidence_gap",
            "真实证据补全验证包",
            f"当前 {keyword} 的真实来源不足以支持具体改型建议，下一步应先补充评论、竞品和供应商证据。",
            "真实来源缺口",
            42,
            24,
            "low",
            38,
            "调研阶段团队",
            ["补采评论源", "补采竞品价格", "补采供应商报价"],
        )

    return [
        InnovationIdea(
            id=str(uuid4()),
            opportunity_id=opportunity_id,
            idea_title=str(item["title"]),
            idea_description=str(item["description"]),
            market_value_score=int(item["market_value"]),
            difficulty_score=int(item["difficulty"]),
            cost_impact=str(item["cost"]),
            differentiation_score=int(item["differentiation"]),
            target_user=str(item["target_user"]),
            suggested_features=list(item["features"]),  # type: ignore[arg-type]
            created_at=now(),
        )
        for item in candidates[:6]
    ]


def score_opportunity(
    trend: TrendData,
    patents: list[Patent],
    competitors: list[Competitor],
    supply_chain: list[SupplyChainItem],
    ideas: list[InnovationIdea],
) -> dict[str, int | str]:
    market_demand = min(95, max(25, int(trend.monthly_search_volume / 1800)))
    trend_score = trend.trend_score
    if competitors:
        avg_rating = sum(item.rating or 0 for item in competitors) / len(competitors)
        competition_score = max(35, min(92, int(110 - avg_rating * 12 - len(competitors) * 2)))
    else:
        competition_score = 50
    active_patents = sum(1 for item in patents if item.legal_status == "active")
    patent_risk_score = max(25, 92 - active_patents * 6)
    innovation_score = int(sum(item.differentiation_score for item in ideas) / len(ideas))
    supply_chain_score = int(sum(item.production_maturity_score for item in supply_chain) / len(supply_chain)) if supply_chain else 35
    competitor_prices = [item.price for item in competitors if item.price > 0]
    if competitor_prices and supply_chain:
        supplier_prices = [item.unit_price_max for item in supply_chain]
        gross_gap = (sum(competitor_prices) / len(competitor_prices)) - (sum(supplier_prices) / len(supplier_prices))
        profit_score = max(35, min(94, int(gross_gap * 2.5)))
    elif competitor_prices:
        profit_score = 55
    else:
        profit_score = 40
    total = round(
        market_demand * 0.20
        + trend_score * 0.15
        + competition_score * 0.20
        + patent_risk_score * 0.10
        + innovation_score * 0.15
        + supply_chain_score * 0.10
        + profit_score * 0.10
    )
    level = "strongly_recommended" if total >= 82 else "recommended" if total >= 72 else "normal" if total >= 60 else "not_recommended"
    return {
        "market_demand_score": market_demand,
        "trend_score": trend_score,
        "competition_score": competition_score,
        "patent_risk_score": patent_risk_score,
        "innovation_score": innovation_score,
        "supply_chain_score": supply_chain_score,
        "profit_score": profit_score,
        "opportunity_score": total,
        "recommendation_level": level,
    }


def build_agent_context(
    keyword: str,
    trend: TrendData,
    patents: list[Patent],
    competitors: list[Competitor],
    pain_points: list[PainPoint],
    supply_chain: list[SupplyChainItem],
) -> dict[str, object]:
    return {
        "keyword": keyword,
        "trend": {
            "source": trend.source,
            "growth_rate": trend.growth_rate,
            "trend_score": trend.trend_score,
            "monthly_search_volume": trend.monthly_search_volume,
            "related_keywords": trend.related_keywords[:8],
        },
        "patents": [
            {
                "title": item.patent_title,
                "number": item.patent_number,
                "status": item.legal_status,
                "risk": item.risk_level,
                "abstract": item.abstract[:300],
            }
            for item in patents[:8]
        ],
        "competitors": [
            {
                "title": item.product_title,
                "platform": item.platform,
                "price": item.price,
                "rating": item.rating,
                "review_count": item.review_count,
            }
            for item in competitors[:8]
        ],
        "pain_points": [
            {
                "point": item.pain_point,
                "frequency": item.frequency,
                "source": item.source,
                "examples": item.example_reviews[:1],
            }
            for item in pain_points[:6]
        ],
        "suppliers": [
            {
                "supplier": item.supplier_name,
                "platform": item.platform,
                "product": item.product_title,
                "price_min": item.unit_price_min,
                "price_max": item.unit_price_max,
                "moq": item.moq,
                "location": item.location,
                "maturity": item.production_maturity_score,
            }
            for item in supply_chain[:10]
        ],
    }


def build_report(
    task: SearchTask,
    opportunity: Opportunity,
    trend: TrendData,
    patents: list[Patent],
    competitors: list[Competitor],
    pain_points: list[PainPoint],
    supply_chain: list[SupplyChainItem],
    ideas: list[InnovationIdea],
    agent_result: AgentResult | None = None,
) -> Report:
    active_patents = sum(1 for item in patents if item.legal_status == "active")
    competitor_prices = [item.price for item in competitors if item.price > 0]
    price_min = min(competitor_prices) if competitor_prices else 0
    price_max = max(competitor_prices) if competitor_prices else 0
    supplier_min = min(item.unit_price_min for item in supply_chain) if supply_chain else 0
    supplier_max = max(item.unit_price_max for item in supply_chain) if supply_chain else 0
    amazon_review_count = sum(1 for item in pain_points if item.source == "amazon_product_page_reviews")
    reddit_count = sum(1 for item in pain_points if item.source == "reddit_search_rss")
    top_pain_links = pain_points[0].evidence_urls[:3] if pain_points else []
    top_pain_link_text = ", ".join(top_pain_links) if top_pain_links else "No direct review URL was retained for this derived signal."
    agent_suffix = ""
    if agent_result:
        if agent_result.status in {"completed", "completed_with_gaps"}:
            agent_suffix = f" Multi-agent run: {agent_result.provider}/{agent_result.model}."
        elif agent_result.status != "missing_credentials":
            agent_suffix = f" Multi-agent fallback: {agent_result.status}."
    data_quality = build_data_quality(
        trend_rows=[trend],
        patents=patents,
        competitors=competitors,
        pain_points=pain_points,
        supply_chain=supply_chain,
        innovation_ideas=ideas,
        agent_result=agent_result,
    )
    quality_summary = data_quality_markdown(data_quality)
    executive = agent_result.executive_summary if agent_result and agent_result.executive_summary else (
        f"{opportunity.product_name} is based on real-source signals from {trend.source}, "
        f"{len(competitors)} Amazon search listings, {len(patents)} Google Patents references, "
        f"and {len(supply_chain)} B2B supplier listings from Alibaba.com/EC21. "
        f"Pain points are extracted from {amazon_review_count} Amazon review-derived clusters, {reddit_count} Reddit-derived clusters, plus source signals. "
        f"The current score is {opportunity.opportunity_score}/100.{agent_suffix}"
    )
    final = agent_result.final_recommendation if agent_result and agent_result.final_recommendation else (
        "Prioritize validation of demand, patent boundaries, and marketplace differentiation before committing spend. "
        "Run professional patent review before commercialization; this analysis is business intelligence only."
    )
    market_analysis = agent_result.market_analysis if agent_result and agent_result.market_analysis else (
        f"Amazon observed price band ${price_min:.2f}-${price_max:.2f}; demand remains attractive if differentiation is visible."
        if competitors
        else "Amazon listing extraction did not return structured product rows; market pricing requires another run or source."
    )
    trend_analysis = agent_result.trend_analysis if agent_result and agent_result.trend_analysis else (
        f"12-month estimated growth is {trend.growth_rate}% with related keywords: {', '.join(trend.related_keywords[:4])}."
    )
    patent_analysis = agent_result.patent_analysis if agent_result and agent_result.patent_analysis else (
        f"{len(patents)} Google Patents references collected; active-risk count is {active_patents}. Professional review required."
    )
    competitor_analysis = agent_result.competitor_analysis if agent_result and agent_result.competitor_analysis else (
        f"Amazon search returned {len(competitors)} structured listings; ratings cluster around {sum(c.rating for c in competitors) / len(competitors):.1f}."
        if competitors
        else "No structured Amazon listing rows were extracted; competition score is low-confidence."
    )
    pain_analysis = agent_result.pain_point_analysis if agent_result and agent_result.pain_point_analysis else (
        f"Most visible unmet need: {pain_points[0].pain_point}. Source: {pain_points[0].source}. "
        f"Evidence links: {top_pain_link_text}"
    )
    supply_analysis = agent_result.supply_chain_analysis if agent_result and agent_result.supply_chain_analysis else (
        f"Alibaba.com/EC21 returned {len(supply_chain)} supplier rows; supplier maturity average: {sum(s.production_maturity_score for s in supply_chain) / len(supply_chain):.0f}/100."
        if supply_chain
        else "No reliable supplier rows were returned; no synthetic supply-chain data is included in this real-source run."
    )
    innovation_analysis = agent_result.innovation_analysis if agent_result and agent_result.innovation_analysis else (
        f"{len(ideas)} innovation ideas generated; strongest: {ideas[0].idea_title}."
    )
    markdown = f"""# {opportunity.product_name} Opportunity Report

## 1. Executive Summary
{executive}

## 2. Product Opportunity Overview
{opportunity.short_description}

## 3. Trend Analysis
{trend_analysis}

## 4. Market and Competitor Analysis
{market_analysis}

{competitor_analysis}

## 5. User Pain Point Analysis
{pain_analysis}

## 6. Patent Intelligence
{patent_analysis}

## 7. Supply Chain Analysis
{supply_analysis}

## 8. Innovation Suggestions
{innovation_analysis}

## 9. Opportunity Score
Overall score: {opportunity.opportunity_score}/100. Recommendation: {opportunity.recommendation_level}.
{agent_result.score_reasoning if agent_result and agent_result.score_reasoning else ""}

## 10. Final Recommendation
{final}

## 11. Data Sources and Confidence
{quality_summary}

## 12. Risk Notice
{agent_result.risk_notice if agent_result and agent_result.risk_notice else "OpportunityOS provides commercial intelligence and AI suggestions, not legal, investment, or patent infringement advice."}
"""
    return Report(
        id=str(uuid4()),
        search_task_id=task.id,
        opportunity_id=opportunity.id,
        user_id=task.user_id,
        report_title=f"{opportunity.product_name} Opportunity Report",
        executive_summary=executive,
        market_analysis=market_analysis,
        trend_analysis=trend_analysis,
        patent_analysis=patent_analysis,
        competitor_analysis=competitor_analysis,
        pain_point_analysis=pain_analysis,
        supply_chain_analysis=supply_analysis,
        innovation_analysis=innovation_analysis,
        final_recommendation=final,
        data_quality_summary=quality_summary,
        data_quality=data_quality,
        agent_run=agent_result.to_trace() if agent_result else {},
        report_score=opportunity.opportunity_score,
        markdown_content=markdown,
        status="completed",
        created_at=now(),
        updated_at=now(),
    )


def run_pipeline(
    request: SearchRequest,
    task_id: str,
    user_id: str,
    progress_callback: Callable[[str, int], None] | None = None,
) -> tuple[
    SearchTask,
    Opportunity,
    list[TrendData],
    list[Patent],
    list[Competitor],
    list[PainPoint],
    list[SupplyChainItem],
    list[InnovationIdea],
    Report,
]:
    def emit(step: str, progress: int) -> None:
        if progress_callback:
            progress_callback(step, progress)

    created_at = now()
    opportunity_id = str(uuid4())
    emit("keyword_expanding", 8)
    related = expand_keywords(request.keyword)
    task = SearchTask(
        id=task_id,
        user_id=user_id,
        keyword=request.keyword,
        industry=request.industry,
        target_market=request.target_market,
        language=request.language,
        status="pending",
        progress=1,
        current_step="pending",
        started_at=created_at,
        finished_at=None,
        created_at=created_at,
        updated_at=now(),
    )
    emit("collecting_trends", 16)
    trend = generate_trend_data(opportunity_id, related[0], request.target_market, related)
    emit("collecting_patents", 28)
    patents = generate_patents(opportunity_id, related[0])
    emit("collecting_competitors", 40)
    competitors = generate_competitors(opportunity_id, related[0])
    emit("collecting_reviews", 52)
    asins = [str(item.raw_data.get("asin", "")) for item in competitors]
    amazon_reviews = collect_amazon_product_reviews(asins, limit=12, reviews_per_asin=3)
    reddit_reviews = collect_reddit_pain_posts(related[0], limit=12)
    reviews = [*amazon_reviews, *reddit_reviews]
    pain_points = generate_pain_points(opportunity_id, related[0], patents, competitors, trend.related_keywords, reviews)
    emit("collecting_supply_chain", 64)
    supply_chain = generate_supply_chain(opportunity_id, related[0], user_id=user_id)
    emit("analyzing", 76)
    agent_context = build_agent_context(related[0], trend, patents, competitors, pain_points, supply_chain)
    ai_agent_allowed, ai_agent_skip_reason = _ai_agent_budget_status(user_id)
    agent_result = (
        run_opportunity_analysis(agent_context)
        if ai_agent_allowed
        else skipped_agent_result(ai_agent_skip_reason or "AI Agent 已被成本护栏跳过。")
    )
    ideas = generate_innovation_ideas(opportunity_id, related[0], pain_points, patents, competitors, supply_chain, agent_result)
    emit("scoring", 86)
    scores = score_opportunity(trend, patents, competitors, supply_chain, ideas)
    if ai_agent_allowed:
        agent_result = finalize_opportunity_agent(
            agent_context,
            agent_result,
            scores,
            [
                {
                    "title": item.idea_title,
                    "description": item.idea_description,
                    "market_value_score": item.market_value_score,
                    "difficulty_score": item.difficulty_score,
                    "cost_impact": item.cost_impact,
                    "differentiation_score": item.differentiation_score,
                    "target_user": item.target_user,
                }
                for item in ideas
            ],
        )
    competitor_prices = [item.price for item in competitors if item.price > 0]
    price_min = min(competitor_prices) if competitor_prices else 0
    price_max = max(competitor_prices) if competitor_prices else 0
    opportunity = Opportunity(
        id=opportunity_id,
        search_task_id=task.id,
        user_id=user_id,
        product_name=related[0].title(),
        product_category=request.industry or "Consumer Product",
        short_description=(
            f"Real-source opportunity direction for {related[0]}, combining public demand signals, Google Patents references, "
            "Amazon listing/review signals, Reddit discussion signals, Alibaba.com/EC21 supplier listings, and innovation potential."
        ),
        opportunity_score=int(scores["opportunity_score"]),
        market_demand_score=int(scores["market_demand_score"]),
        trend_score=int(scores["trend_score"]),
        competition_score=int(scores["competition_score"]),
        patent_risk_score=int(scores["patent_risk_score"]),
        innovation_score=int(scores["innovation_score"]),
        supply_chain_score=int(scores["supply_chain_score"]),
        profit_score=int(scores["profit_score"]),
        recommendation_level=str(scores["recommendation_level"]),  # type: ignore[arg-type]
        estimated_price_min=price_min,
        estimated_price_max=price_max,
        estimated_market_size="Real-source demand index; market size requires paid data enrichment",
        main_markets=["United States", "Germany", "United Kingdom", "Canada"],
        suitable_platforms=["Amazon", "Shopify DTC", "Google Search", "Content SEO"],
        created_at=now(),
        updated_at=now(),
    )
    emit("generating_report", 94)
    report = build_report(task, opportunity, trend, patents, competitors, pain_points, supply_chain, ideas, agent_result)
    task.opportunity_id = opportunity.id
    task.report_id = report.id
    task.status = "completed"
    task.progress = 100
    task.current_step = "completed"
    task.finished_at = now()
    task.updated_at = now()
    return task, opportunity, [trend], patents, competitors, pain_points, supply_chain, ideas, report
