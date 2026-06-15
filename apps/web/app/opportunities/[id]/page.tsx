"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  BadgeDollarSign,
  Bookmark,
  BookmarkCheck,
  ChevronDown,
  CheckCircle2,
  CircleAlert,
  Database,
  Download,
  ExternalLink,
  FileText,
  FlaskConical,
  Gauge,
  ListChecks,
  Loader2,
  PackageCheck,
  Percent,
  Rocket,
  ScrollText,
  ShieldCheck,
  ShoppingCart,
  Target,
  TimerReset,
  TrendingUp,
  Workflow,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { EmptyState, MetricCard, ScoreBar, Section } from "@/components/ui";
import { API_BASE_URL, api, type DataQualitySource, type OpportunityDetail } from "@/lib/api";

const recommendationLabels = {
  not_recommended: "不推荐",
  normal: "普通",
  recommended: "推荐",
  strongly_recommended: "强烈推荐",
};

const downloadFormats = [
  ["markdown", "Markdown"],
  ["pdf", "PDF"],
  ["excel", "Excel"],
  ["word", "Word"],
] as const;

const recommendationTone = {
  not_recommended: "text-clay bg-clay/10 border-clay/20",
  normal: "text-muted bg-field border-line",
  recommended: "text-indigo bg-indigo/10 border-indigo/15",
  strongly_recommended: "text-emerald-700 bg-emerald-50 border-emerald-100",
};

function riskLabel(value: unknown) {
  if (value === "high") return "高风险";
  if (value === "medium") return "中风险";
  if (value === "low") return "低风险";
  return "待确认";
}

function patentStatusLabel(value: string) {
  const labels: Record<string, string> = {
    active: "有效",
    expired: "已失效",
    expiring_soon: "临近到期",
    possibly_expired: "可能失效",
    unknown: "待确认",
  };
  return labels[value] ?? value;
}

function platformLabel(value: string) {
  const labels: Record<string, string> = {
    amazon: "Amazon",
    aliexpress: "AliExpress",
    temu: "Temu",
    tiktok_shop: "TikTok Shop",
  };
  return labels[value] ?? value;
}

function sourceLabel(value: string) {
  const labels: Record<string, string> = {
    amazon_product_page_reviews: "Amazon Reviews",
    reddit_search_rss: "Reddit",
    patent_and_listing_signals: "Patent + Listing",
    amazon_listing_signals: "Amazon Listing",
    suggest_and_patent_signals: "Suggest + Patent",
    real_source_gap: "Low Confidence",
  };
  return labels[value] ?? value;
}

function decisionCopy(score: number, recommendation: keyof typeof recommendationLabels) {
  if (score >= 80 || recommendation === "strongly_recommended") {
    return "进入样品验证，优先确认专利边界与首批供应商报价。";
  }
  if (score >= 65 || recommendation === "recommended") {
    return "进入小规模验证，用用户痛点和竞品弱点校准差异化卖点。";
  }
  if (score >= 50) {
    return "先做轻量调研，只有当需求与利润信号继续增强时再推进。";
  }
  return "暂缓投入，把该机会放入观察池，等待更强趋势或供应链信号。";
}

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function confidenceLabel(value: string) {
  if (value === "high") return "高可信";
  if (value === "medium") return "中可信";
  return "低可信";
}

function confidenceUserNote(value: string) {
  if (value === "high") return "证据覆盖较完整，可直接进入验证计划。";
  if (value === "medium") return "证据足以支持初步判断，建议用下方验证计划继续确认关键假设。";
  return "当前只适合作为早期观察信号，建议先补充需求、竞品或供应链证据后再投入。";
}

function sourceStatusLabel(value: string) {
  const labels: Record<string, string> = {
    ok: "已采集",
    empty: "无结果",
    guarded: "需会话",
    missing_credentials: "未配置",
    timeout: "超时",
    not_recorded: "未记录",
  };
  return labels[value] ?? value;
}

function sourcePublicStatusLabel(value: string) {
  if (value === "ok") return "已验证";
  if (value === "empty") return "暂无证据";
  if (value === "guarded" || value === "missing_credentials" || value === "not_recorded") return "待补证据";
  if (value === "timeout") return "待复核";
  return "待复核";
}

function sourceStatusClass(value: string) {
  if (value === "ok") return "border-indigo/15 bg-indigo/10 text-indigo";
  if (value === "guarded" || value === "missing_credentials" || value === "not_recorded") return "border-amber-200 bg-amber-50 text-amber-700";
  return "border-clay/20 bg-clay/10 text-clay";
}

function sourceEvidenceLabel(source: DataQualitySource) {
  return source.count > 0 ? `${source.count} 条证据` : "暂未形成有效证据";
}

function sourcePublicNote(source: DataQualitySource) {
  if (source.count > 0) return source.note;
  if (source.status === "empty") return "该来源本次未检索到足够相关的公开信号，暂不参与增强评分。";
  if (source.status === "guarded" || source.status === "missing_credentials") {
    return "该来源需要进一步授权或补充数据后才能纳入研判，当前不会影响核心结论。";
  }
  if (source.status === "timeout") return "该来源本次响应不稳定，建议后续重新采集后再复核。";
  return "该来源暂未提供可用于决策的有效证据，当前仅作为后续补证方向。";
}

function sourceDecisionNote(source: DataQualitySource) {
  if (source.count > 0) return "已纳入当前评分、机会判断与验证计划。";
  return "暂不纳入评分，仅作为后续补充证据的参考方向。";
}

export default function OpportunityDetailPage() {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [detail, setDetail] = useState<OpportunityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [expandedValidation, setExpandedValidation] = useState("需求验证");
  const [expandedExperiment, setExpandedExperiment] = useState("WEEK 01");
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});
  const [expandedPatentId, setExpandedPatentId] = useState<string | null>(null);
  const [expandedCompetitorId, setExpandedCompetitorId] = useState<string | null>(null);
  const [expandedPainId, setExpandedPainId] = useState<string | null>(null);
  const [expandedIdeaId, setExpandedIdeaId] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError("");
    api
      .getOpportunity(params.id)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "机会详情加载失败"))
      .finally(() => setLoading(false));
  }, [params.id, user]);

  useEffect(() => {
    if (!user) return;
    api
      .listSaved()
      .then((items) => setSaved(items.some((item) => item.id === params.id)))
      .catch(() => setSaved(false));
  }, [params.id, user]);

  const scoreRows = useMemo(() => {
    if (!detail) return [];
    const item = detail.opportunity;
    return [
      ["市场需求", item.market_demand_score],
      ["趋势增长", item.trend_score],
      ["竞争空间", item.competition_score],
      ["专利安全", item.patent_risk_score],
      ["创新空间", item.innovation_score],
      ["供应链成熟", item.supply_chain_score],
      ["利润空间", item.profit_score],
    ] as const;
  }, [detail]);

  async function toggleSave() {
    if (!detail) return;
    setSaving(true);
    try {
      if (saved) {
        await api.unsaveOpportunity(detail.opportunity.id);
        setSaved(false);
      } else {
        await api.saveOpportunity(detail.opportunity.id, "Saved from opportunity decision workspace");
        setSaved(true);
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <AppShell>
        <Section title="机会详情">
          <div className="flex items-center gap-2 text-muted">
            <Loader2 className="animate-spin" size={18} />
            正在加载机会分析...
          </div>
        </Section>
      </AppShell>
    );
  }

  if (error || !detail) {
    return (
      <AppShell>
        <EmptyState title="未找到机会" description={error || "请回到机会探索页重新生成报告。"} />
      </AppShell>
    );
  }

  const opportunity = detail.opportunity;
  const trend = detail.trend_data[0];
  const selectedPatentId = expandedPatentId ?? detail.patents[0]?.id ?? null;
  const selectedCompetitorId = expandedCompetitorId ?? detail.competitors[0]?.id ?? null;
  const selectedPainId = expandedPainId ?? detail.pain_points[0]?.id ?? null;
  const selectedIdeaId = expandedIdeaId ?? detail.innovation_ideas[0]?.id ?? null;
  const recommendation = recommendationLabels[opportunity.recommendation_level];
  const recommendationClass = recommendationTone[opportunity.recommendation_level];
  const decision = decisionCopy(opportunity.opportunity_score, opportunity.recommendation_level);
  const bestIdea = [...detail.innovation_ideas].sort(
    (a, b) => b.market_value_score + b.differentiation_score - b.difficulty_score - (a.market_value_score + a.differentiation_score - a.difficulty_score),
  )[0];
  const topPain = [...detail.pain_points].sort((a, b) => b.frequency - a.frequency)[0];
  const topSupplier = [...detail.supply_chain].sort((a, b) => b.production_maturity_score - a.production_maturity_score)[0];
  const averageSupplyCost =
    detail.supply_chain.length > 0
      ? detail.supply_chain.reduce((sum, item) => sum + (item.unit_price_min + item.unit_price_max) / 2, 0) / detail.supply_chain.length
      : opportunity.estimated_price_min * 0.32;
  const targetRetailPrice = (opportunity.estimated_price_min + opportunity.estimated_price_max) / 2;
  const estimatedGrossMargin = clampPercent(((targetRetailPrice - averageSupplyCost) / Math.max(1, targetRetailPrice)) * 100);
  const entryChannels = [...opportunity.suitable_platforms, ...opportunity.main_markets].slice(0, 6);
  const validationSteps = [
    {
      icon: Target,
      label: "需求验证",
      title: topPain ? topPain.pain_point : "确认高频用户痛点",
      detail: topPain ? topPain.ai_summary : "从评论、论坛和搜索词里确认用户愿意为哪个痛点付费。",
    },
    {
      icon: ShieldCheck,
      label: "边界验证",
      title: `${riskLabel(detail.patent_summary.risk_level)}专利路线`,
      detail: `优先复核 ${detail.patent_summary.high_risk ?? 0} 条高风险引用，避开活跃权利要求密集区。`,
    },
    {
      icon: Workflow,
      label: "方案验证",
      title: bestIdea ? bestIdea.idea_title : "形成最小差异化方案",
      detail: bestIdea ? bestIdea.idea_description : "把竞品弱点转译为一个可以快速打样的核心功能。",
    },
  ];
  const businessSignals = [
    {
      icon: ShoppingCart,
      label: "目标售价",
      value: `$${targetRetailPrice.toFixed(0)}`,
      detail: `建议价格带 $${opportunity.estimated_price_min.toFixed(0)}-${opportunity.estimated_price_max.toFixed(0)}`,
    },
    {
      icon: PackageCheck,
      label: "估算采购成本",
      value: `$${averageSupplyCost.toFixed(1)}`,
      detail: topSupplier ? `${topSupplier.supplier_name} 成熟度 ${topSupplier.production_maturity_score}` : "等待供应商数据补齐",
    },
    {
      icon: Percent,
      label: "粗略毛利空间",
      value: `${estimatedGrossMargin}%`,
      detail: estimatedGrossMargin >= 55 ? "具备广告测试空间" : "需要压低采购或物流成本",
    },
  ];
  const experimentPlan = [
    {
      label: "WEEK 01",
      title: "痛点与关键词验证",
      detail: topPain ? `围绕“${topPain.pain_point}”做 12 条评论证据归因。` : "收集评论证据并确认用户愿意付费的问题。",
      metric: "30+ 有效评论证据",
    },
    {
      label: "WEEK 02",
      title: "专利与竞品拆解",
      detail: "复核高风险专利，拆解 6 个竞品的功能、定价和差评集中区。",
      metric: `${detail.patent_summary.high_risk ?? 0} 条高风险专利复核`,
    },
    {
      label: "WEEK 03",
      title: "供应商与样品确认",
      detail: topSupplier ? `优先联系 ${topSupplier.supplier_name}，确认 MOQ、交期和改款空间。` : "联系 3 家供应商确认 MOQ、交期和改款空间。",
      metric: "3 家供应商报价",
    },
    {
      label: "WEEK 04",
      title: "落地页与广告小测",
      detail: bestIdea ? `用“${bestIdea.idea_title}”作为首轮差异化主张。` : "用一个核心差异化主张做落地页和广告小测。",
      metric: "CTR / CVR 达标再推进",
    },
  ];
  const gateChecks = [
    {
      passed: trend.trend_score >= 65,
      label: "趋势分 >= 65",
      detail: `当前 ${trend.trend_score}`,
    },
    {
      passed: estimatedGrossMargin >= 45,
      label: "粗略毛利 >= 45%",
      detail: `当前 ${estimatedGrossMargin}%`,
    },
    {
      passed: opportunity.competition_score >= 40,
      label: "竞争空间 >= 40",
      detail: `当前 ${opportunity.competition_score}`,
    },
    {
      passed: detail.supply_chain.length >= 3,
      label: "可选供应商 >= 3",
      detail: `当前 ${detail.supply_chain.length} 家`,
    },
  ];
  const chartValues = trend.monthly_data.map((item) => item.value);
  const chartMax = Math.max(...chartValues);
  const chartMin = Math.min(...chartValues);
  const chartRange = Math.max(1, chartMax - chartMin);
  const chartPoints = trend.monthly_data
    .map((item, index) => {
      const x = 24 + (index / Math.max(1, trend.monthly_data.length - 1)) * 552;
      const y = 224 - ((item.value - chartMin) / chartRange) * 176;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const chartAreaPoints = `24,240 ${chartPoints} 576,240`;

  return (
    <AppShell>
      <div className="mb-6 flex flex-col justify-between gap-5 rounded-2xl border border-line/80 bg-white p-7 shadow-panel lg:flex-row">
        <div>
          <div className="mb-3 flex flex-wrap gap-2 text-sm">
            <span className="rounded-lg border border-line bg-field px-3 py-1.5 font-medium text-muted">{opportunity.product_category}</span>
            <span className={`rounded-lg border px-3 py-1.5 font-semibold ${recommendationClass}`}>{recommendation}</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-normal text-ink md:text-5xl">{opportunity.product_name}</h1>
          <p className="mt-4 max-w-3xl text-base leading-8 text-muted">{opportunity.short_description}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={toggleSave}
            disabled={saving}
            className="focus-ring inline-flex items-center gap-2 rounded-xl border border-line bg-white px-4 py-3 text-sm font-semibold text-ink transition hover:bg-field"
          >
            {saved ? <BookmarkCheck size={16} className="text-indigo" /> : <Bookmark size={16} />}
            {saving ? "处理中" : saved ? "已收藏" : "收藏"}
          </button>
          <Link
            href={`/reports/${detail.report_id}`}
            className="focus-ring inline-flex items-center gap-2 rounded-xl bg-gradient-to-br from-indigo to-violet px-4 py-3 text-sm font-semibold text-white shadow-glow"
          >
            <FileText size={16} />
            报告
          </Link>
        </div>
      </div>

      <div className="mb-6 grid gap-5 xl:grid-cols-[1fr_1.35fr_0.9fr]">
        <section className="relative overflow-hidden rounded-2xl border border-line/80 bg-white p-6 shadow-panel">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_12%,rgba(91,92,246,0.10),transparent_34%),linear-gradient(135deg,rgba(255,255,255,0.98),rgba(250,250,252,0.84))]" />
          <div className="relative">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-muted">决策建议</p>
              <span className={`rounded-full border px-3 py-1 text-xs font-bold ${recommendationClass}`}>{recommendation}</span>
            </div>
            <div className="mt-5 flex items-end gap-3">
              <p className="electric-text text-6xl font-semibold">{opportunity.opportunity_score}</p>
              <p className="pb-3 text-sm font-semibold text-muted">/100</p>
            </div>
            <p className="mt-5 text-lg font-semibold leading-7 text-ink">{decision}</p>
            <div className="mt-5 grid gap-2 text-sm text-muted">
              <p className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-indigo" />
                趋势增长 {trend.growth_rate}% · 月搜索 {trend.monthly_search_volume.toLocaleString()}
              </p>
              <p className="flex items-center gap-2">
                <CircleAlert size={16} className="text-clay" />
                专利风险 {riskLabel(detail.patent_summary.risk_level)}
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-line/80 bg-white p-6 shadow-panel">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-muted">验证优先级</p>
              <h2 className="mt-1 text-xl font-semibold text-ink">先验证最能改变决策的 3 件事</h2>
            </div>
            <Rocket className="text-indigo" size={24} />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {validationSteps.map((step) => {
              const Icon = step.icon;
              const expanded = expandedValidation === step.label;
              return (
                <button
                  key={step.label}
                  type="button"
                  aria-expanded={expanded}
                  onClick={() =>
                    setExpandedValidation((current) =>
                      current === step.label ? "" : step.label,
                    )
                  }
                  className={`focus-ring group h-full rounded-xl border bg-gradient-to-br p-4 text-left transition hover:-translate-y-0.5 hover:border-indigo/30 hover:shadow-panel ${
                    expanded ? "border-indigo/30 from-white to-indigo/5 shadow-panel" : "border-line from-white to-field/70"
                  }`}
                >
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <span className="rounded-full bg-indigo/10 px-2.5 py-1 text-xs font-bold text-indigo">{step.label}</span>
                    <span className="flex items-center gap-2 text-indigo">
                      <Icon size={18} />
                      <ChevronDown
                        size={16}
                        className={`transition-transform ${expanded ? "rotate-180" : ""}`}
                      />
                    </span>
                  </div>
                  <p className="text-sm font-semibold leading-6 text-ink">{step.title}</p>
                  <p className={`mt-2 text-sm leading-6 text-muted ${expanded ? "" : "line-clamp-3"}`}>
                    {step.detail}
                  </p>
                  <span className="mt-3 inline-flex text-xs font-semibold text-indigo opacity-80 transition group-hover:opacity-100">
                    {expanded ? "收起详情" : "展开完整验证依据"}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section className="rounded-2xl border border-line/80 bg-white p-6 shadow-panel">
          <p className="text-sm font-semibold text-muted">市场入口</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {entryChannels.map((item) => (
              <span key={item} className="rounded-lg border border-line bg-field px-3 py-1.5 text-sm font-semibold text-ink/80">
                {item}
              </span>
            ))}
          </div>
          <div className="mt-6 grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-field p-4">
              <p className="text-xs font-semibold text-muted">建议价格带</p>
              <p className="mt-2 text-lg font-semibold text-ink">
                ${opportunity.estimated_price_min.toFixed(0)}-${opportunity.estimated_price_max.toFixed(0)}
              </p>
            </div>
            <div className="rounded-xl bg-field p-4">
              <p className="text-xs font-semibold text-muted">供应成熟度</p>
              <p className="electric-text mt-2 text-lg font-semibold">{opportunity.supply_chain_score}</p>
            </div>
          </div>
          <a
            href={`${API_BASE_URL}/api/reports/${detail.report_id}/download?format=markdown`}
            className="focus-ring mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-line bg-white px-4 py-3 text-sm font-semibold text-ink transition hover:bg-field"
          >
            <Download size={16} />
            下载 Markdown
          </a>
        </section>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="机会总分" value={opportunity.opportunity_score} detail="加权综合评分" icon={Gauge} />
        <MetricCard label="趋势增长" value={`${trend.growth_rate}%`} detail={`${trend.monthly_search_volume.toLocaleString()} 月搜索估算`} icon={TrendingUp} />
        <MetricCard label="专利引用" value={String(detail.patent_summary.total)} detail={riskLabel(detail.patent_summary.risk_level)} icon={ScrollText} />
        <MetricCard
          label="价格区间"
          value={`$${opportunity.estimated_price_min.toFixed(0)}-$${opportunity.estimated_price_max.toFixed(0)}`}
          detail={opportunity.estimated_market_size}
          icon={BadgeDollarSign}
        />
      </div>

      <div className="mt-6">
        <Section
          title="数据来源可信度"
          action={
            <span className={`rounded-full border px-3 py-1.5 text-xs font-bold ${detail.data_quality.confidence_level === "high" ? "border-indigo/20 bg-indigo/10 text-indigo" : detail.data_quality.confidence_level === "medium" ? "border-violet/20 bg-[#F4F0FF] text-violet" : "border-clay/20 bg-clay/10 text-clay"}`}>
              {confidenceLabel(detail.data_quality.confidence_level)}
            </span>
          }
        >
          <div className="grid gap-4 xl:grid-cols-[0.45fr_1fr]">
            <div className="rounded-xl border border-line bg-gradient-to-br from-white to-field/70 p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-muted">覆盖评分</p>
                  <p className="electric-text mt-2 text-5xl font-semibold">{detail.data_quality.confidence_score}</p>
                </div>
                <span className="grid size-12 place-items-center rounded-full bg-indigo/10 text-indigo">
                  <Database size={22} />
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-muted">
                {Object.entries(detail.data_quality.evidence_counts).map(([key, value]) => (
                  <div key={key} className="rounded-lg bg-white px-3 py-2">
                    <p className="font-semibold text-ink">{value}</p>
                    <p className="mt-1">{key.replaceAll("_", " ")}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {detail.data_quality.sources.map((source) => {
                const expanded = Boolean(expandedSources[source.key]);
                return (
                  <button
                    key={source.key}
                    type="button"
                    aria-expanded={expanded}
                    onClick={() =>
                      setExpandedSources((current) => ({
                        ...current,
                        [source.key]: !current[source.key],
                      }))
                    }
                    className={`focus-ring group rounded-xl border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-indigo/30 hover:shadow-panel ${
                      expanded ? "border-indigo/30 shadow-panel" : "border-line"
                    }`}
                  >
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-ink">{source.label}</p>
                        <p className="mt-1 text-xs text-muted">{source.category}</p>
                      </div>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold ${sourceStatusClass(source.status)}`}>
                          {sourcePublicStatusLabel(source.status)}
                        </span>
                        <ChevronDown
                          size={15}
                          className={`text-indigo transition-transform ${expanded ? "rotate-180" : ""}`}
                        />
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-indigo">{sourceEvidenceLabel(source)}</p>
                    <p className={`mt-2 text-xs leading-5 text-muted ${expanded ? "" : "line-clamp-2"}`}>
                      {sourcePublicNote(source)}
                    </p>
                    <span className="mt-3 inline-flex text-xs font-semibold text-indigo opacity-80 transition group-hover:opacity-100">
                      {expanded ? "收起来源说明" : "展开来源说明"}
                    </span>
                    {expanded ? (
                      <div className="mt-3 rounded-lg bg-field px-3 py-2 text-xs leading-5 text-muted">
                        <p>研判影响：{sourceDecisionNote(source)}</p>
                        {user?.role === "admin" ? (
                          <details className="mt-2">
                            <summary className="cursor-pointer font-semibold text-ink">采集诊断</summary>
                            <div className="mt-2 rounded-md bg-white px-2 py-2">
                              <p>原始状态：{sourceStatusLabel(source.status)}</p>
                              <p className="mt-1">原始说明：{source.note}</p>
                            </div>
                          </details>
                        ) : null}
                      </div>
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="mt-4 rounded-xl border border-line bg-field/70 p-4">
            <p className="text-sm font-semibold text-ink">可信度提示</p>
            <p className="mt-2 text-sm leading-6 text-muted">
              {confidenceUserNote(detail.data_quality.confidence_level)}
            </p>
          </div>
          {user?.role === "admin" && detail.data_quality.gaps.length ? (
            <details className="mt-3 rounded-xl border border-amber-200 bg-amber-50/70 p-4">
              <summary className="cursor-pointer text-sm font-semibold text-amber-800">
                内部诊断：证据缺口 {detail.data_quality.gaps.length} 项
              </summary>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {detail.data_quality.gaps.map((gap) => (
                  <p key={gap} className="text-sm leading-6 text-amber-800/80">
                    {gap}
                  </p>
                ))}
              </div>
            </details>
          ) : null}
        </Section>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[0.9fr_1.4fr_0.9fr]">
        <Section title="商业测算">
          <div className="space-y-3">
            {businessSignals.map((signal) => {
              const Icon = signal.icon;
              return (
                <div key={signal.label} className="flex items-center justify-between gap-4 rounded-xl border border-line bg-gradient-to-br from-white to-field/70 p-4">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="grid size-10 shrink-0 place-items-center rounded-full bg-indigo/10 text-indigo">
                      <Icon size={18} />
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-ink">{signal.label}</p>
                      <p className="mt-1 truncate text-xs text-muted">{signal.detail}</p>
                    </div>
                  </div>
                  <p className="electric-text shrink-0 text-2xl font-semibold">{signal.value}</p>
                </div>
              );
            })}
          </div>
        </Section>

        <Section title="30 天验证实验">
          <div className="grid gap-3 md:grid-cols-2">
            {experimentPlan.map((step) => {
              const expanded = expandedExperiment === step.label;
              return (
                <button
                  key={step.label}
                  type="button"
                  aria-expanded={expanded}
                  onClick={() =>
                    setExpandedExperiment((current) =>
                      current === step.label ? "" : step.label,
                    )
                  }
                  className={`focus-ring group rounded-xl border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-indigo/30 hover:shadow-panel ${
                    expanded ? "border-indigo/30 shadow-panel" : "border-line"
                  }`}
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <span className="rounded-full bg-indigo/10 px-2.5 py-1 text-xs font-bold text-indigo">{step.label}</span>
                    <span className="flex items-center gap-2 text-indigo">
                      <FlaskConical size={17} />
                      <ChevronDown
                        size={15}
                        className={`transition-transform ${expanded ? "rotate-180" : ""}`}
                      />
                    </span>
                  </div>
                  <p className="font-semibold text-ink">{step.title}</p>
                  <p className={`mt-2 text-sm leading-6 text-muted ${expanded ? "" : "line-clamp-2"}`}>
                    {step.detail}
                  </p>
                  <p className="mt-3 inline-flex items-center gap-2 rounded-lg bg-field px-2.5 py-1 text-xs font-semibold text-muted">
                    <TimerReset size={13} />
                    {step.metric}
                  </p>
                  {expanded ? (
                    <div className="mt-3 rounded-lg bg-indigo/5 px-3 py-2 text-xs leading-5 text-muted">
                      <p className="font-semibold text-ink">交付物</p>
                      <p className="mt-1">
                        输出一页验证记录：证据截图、判断标准、通过/不通过结论，以及下一周是否继续投入。
                      </p>
                    </div>
                  ) : null}
                  <span className="mt-3 inline-flex text-xs font-semibold text-indigo opacity-80 transition group-hover:opacity-100">
                    {expanded ? "收起实验细节" : "展开实验细节"}
                  </span>
                </button>
              );
            })}
          </div>
        </Section>

        <Section title="Go / No-Go 门槛">
          <div className="space-y-3">
            {gateChecks.map((item) => (
              <div key={item.label} className="flex items-start gap-3 rounded-xl border border-line bg-white p-4 shadow-sm">
                <span className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-full ${item.passed ? "bg-indigo/10 text-indigo" : "bg-clay/10 text-clay"}`}>
                  {item.passed ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">{item.label}</p>
                  <p className="mt-1 text-xs text-muted">{item.detail}</p>
                </div>
              </div>
            ))}
            <p className="rounded-xl bg-field p-4 text-sm leading-6 text-muted">
              <ListChecks className="mr-2 inline text-indigo" size={16} />
              通过 3 项以上再进入打样；低于 3 项建议继续观察或更换切入点。
            </p>
          </div>
        </Section>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Section title="趋势分析">
          <div className="h-[320px] rounded-xl border border-line bg-gradient-to-br from-white to-field/60 p-4">
            <svg viewBox="0 0 600 270" className="h-full w-full" role="img" aria-label="12个月趋势折线图">
              <defs>
                <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5B5CF6" stopOpacity="0.28" />
                  <stop offset="100%" stopColor="#5B5CF6" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              {[48, 92, 136, 180, 224].map((y) => (
                <line key={y} x1="24" x2="576" y1={y} y2={y} stroke="#E8EAF1" strokeWidth="1" />
              ))}
              <polygon points={chartAreaPoints} fill="url(#trendFill)" />
              <polyline points={chartPoints} fill="none" stroke="#5B5CF6" strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" />
              {trend.monthly_data.map((item, index) => {
                const x = 24 + (index / Math.max(1, trend.monthly_data.length - 1)) * 552;
                const y = 224 - ((item.value - chartMin) / chartRange) * 176;
                return <circle key={item.month} cx={x} cy={y} r={index === trend.monthly_data.length - 1 ? 5 : 3} fill="#5B5CF6" />;
              })}
              {trend.monthly_data.filter((_, index) => index % 2 === 1).map((item, index) => {
                const originalIndex = index * 2 + 1;
                const x = 24 + (originalIndex / Math.max(1, trend.monthly_data.length - 1)) * 552;
                return (
                  <text key={item.month} x={x} y="262" textAnchor="middle" className="fill-muted text-[12px]">
                    {item.month.slice(5)}
                  </text>
                );
              })}
            </svg>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {trend.related_keywords.map((keyword) => (
              <span key={keyword} className="rounded-lg border border-line bg-field px-3 py-1.5 text-sm text-muted">
                {keyword}
              </span>
            ))}
          </div>
        </Section>

        <Section title="机会评分">
          <div className="space-y-4">
            {scoreRows.map(([label, value]) => (
              <ScoreBar key={label} label={label} value={value} />
            ))}
          </div>
        </Section>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Section title="专利情报">
          <div className="space-y-3">
            {detail.patent_summary ? (
              <p className="rounded-xl border border-line bg-field/80 p-4 text-sm leading-6 text-muted">
                共 {detail.patent_summary.total} 条专利引用，活跃 {detail.patent_summary.active} 条，已失效{" "}
                {detail.patent_summary.expired} 条，高风险 {detail.patent_summary.high_risk} 条。
              </p>
            ) : null}
            <div className="max-h-[360px] space-y-2 overflow-auto pr-2">
              {detail.patents.slice(0, 5).map((patent) => {
                const expanded = selectedPatentId === patent.id;
                return (
                <button
                  key={patent.id}
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setExpandedPatentId((current) => (current === patent.id ? "" : patent.id))}
                  className={`focus-ring block w-full rounded-xl border bg-white p-4 text-left shadow-sm transition hover:border-indigo/30 hover:shadow-panel ${
                    expanded ? "border-indigo/30 shadow-panel" : "border-line"
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-medium text-ink">{patent.patent_title}</p>
                      <p className="mt-1 text-sm text-muted">
                        {patent.patent_number} · {patent.applicant}
                      </p>
                    </div>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="rounded-lg bg-indigo/10 px-2 py-1 text-xs font-semibold text-indigo">{patentStatusLabel(patent.legal_status)}</span>
                      <ChevronDown size={15} className={`text-indigo transition-transform ${expanded ? "rotate-180" : ""}`} />
                    </span>
                  </div>
                  <p className={`mt-2 text-sm leading-6 text-muted ${expanded ? "" : "line-clamp-2"}`}>{patent.abstract}</p>
                  {expanded ? (
                    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-field px-3 py-2 text-xs text-muted">
                      <span>申请日 {patent.filing_date || "待确认"}</span>
                      <span>到期 {patent.estimated_expiry_date || "待确认"}</span>
                      <a
                        href={patent.original_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        className="focus-ring inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 font-semibold text-indigo"
                      >
                        <ExternalLink size={13} />
                        打开专利来源
                      </a>
                    </div>
                  ) : null}
                </button>
                );
              })}
              {detail.patent_summary.total ? null : <EmptyState title="暂无专利数据" description="后端尚未返回专利引用。" />}
              {detail.report_id ? null : <p className="text-sm text-clay">报告仍在生成中。</p>}
            </div>
          </div>
        </Section>

        <Section title="竞品分析">
          <div className="space-y-3">
            {detail.competitor_summary.count ? (
              <p className="rounded-xl border border-line bg-field/80 p-4 text-sm leading-6 text-muted">
                找到 {detail.competitor_summary.count} 个竞品，价格区间 ${detail.competitor_summary.price_min}-
                ${detail.competitor_summary.price_max}，平均评分 {detail.competitor_summary.average_rating}。
              </p>
            ) : (
              <EmptyState title="暂无结构化竞品" description="Amazon 搜索未返回可解析 listing；请稍后重试或接入备用竞品源。" />
            )}
            {detail.competitors.slice(0, 5).map((item) => {
              const expanded = selectedCompetitorId === item.id;
              return (
              <button
                key={item.id}
                type="button"
                aria-expanded={expanded}
                onClick={() => setExpandedCompetitorId((current) => (current === item.id ? "" : item.id))}
                className={`focus-ring block w-full rounded-xl border bg-white p-4 text-left shadow-sm transition hover:border-indigo/30 hover:shadow-panel ${
                  expanded ? "border-indigo/30 shadow-panel" : "border-line"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-ink">{item.product_title}</p>
                  <span className="flex shrink-0 items-center gap-2 text-sm text-muted">
                    {platformLabel(item.platform)}
                    <ChevronDown size={15} className={`text-indigo transition-transform ${expanded ? "rotate-180" : ""}`} />
                  </span>
                </div>
                <p className="mt-2 text-sm text-muted">
                  {item.brand} · ${item.price.toFixed(2)} · {item.rating}/5 · {item.review_count.toLocaleString()} reviews
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(expanded ? item.weaknesses : item.weaknesses.slice(0, 2)).map((weakness) => (
                    <span key={weakness} className="rounded-lg bg-field px-2.5 py-1 text-xs font-semibold text-muted">
                      {weakness}
                    </span>
                  ))}
                </div>
                {expanded ? (
                  <div className="mt-3 rounded-lg bg-field px-3 py-2 text-xs leading-5 text-muted">
                    <p>估算销量：{item.estimated_sales.toLocaleString()} · 货币：{item.currency}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {item.main_features.map((feature) => (
                        <span key={feature} className="rounded-md bg-white px-2 py-1 font-semibold text-muted">
                          {feature}
                        </span>
                      ))}
                      <a
                        href={item.product_url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        className="focus-ring inline-flex items-center gap-1 rounded-md bg-white px-2 py-1 font-semibold text-indigo"
                      >
                        <ExternalLink size={13} />
                        打开竞品来源
                      </a>
                    </div>
                  </div>
                ) : null}
              </button>
              );
            })}
          </div>
        </Section>
      </div>

      <div className="mt-6">
        <Section title="供应链分析">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {detail.supply_chain.map((item) => (
              <a key={item.id} href={item.supplier_url} target="_blank" rel="noreferrer" className="rounded-xl border border-line bg-white p-4 shadow-sm transition hover:border-indigo/30">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-ink">{item.supplier_name}</p>
                    <p className="mt-1 text-sm text-muted">{item.platform} · {item.location}</p>
                  </div>
                  <span className="electric-text text-lg font-semibold">{item.production_maturity_score}</span>
                </div>
                <p className="mt-3 text-sm text-muted">
                  ${item.unit_price_min}-${item.unit_price_max} · MOQ {item.moq}
                </p>
              </a>
            ))}
            {detail.supply_chain.length === 0 ? (
              <div className="md:col-span-2 xl:col-span-3">
                <EmptyState title="未返回可靠供应商" description="当前真实 B2B 来源没有返回可用供应商；系统不会生成模拟供应链数据。" />
              </div>
            ) : null}
          </div>
        </Section>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Section title="用户痛点">
          <div className="space-y-3">
            {detail.pain_points.map((point) => {
              const expanded = selectedPainId === point.id;
              return (
              <div key={point.id} className={`rounded-xl border bg-white p-4 shadow-sm transition ${expanded ? "border-indigo/30 shadow-panel" : "border-line"}`}>
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setExpandedPainId((current) => (current === point.id ? "" : point.id))}
                  className="focus-ring w-full rounded-lg text-left"
                >
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-ink">{point.pain_point}</p>
                  <div className="flex items-center gap-2">
                    <span className="rounded-lg bg-field px-2 py-1 text-xs font-semibold text-muted">{sourceLabel(point.source)}</span>
                    <span className="rounded-lg bg-indigo/10 px-2 py-1 text-sm font-semibold text-indigo">{point.frequency}</span>
                    <ChevronDown size={15} className={`text-indigo transition-transform ${expanded ? "rotate-180" : ""}`} />
                  </div>
                </div>
                <p className={`mt-2 text-sm leading-6 text-muted ${expanded ? "" : "line-clamp-2"}`}>{point.ai_summary}</p>
                <span className="mt-2 inline-flex text-xs font-semibold text-indigo">
                  {expanded ? "收起痛点证据" : "展开痛点证据"}
                </span>
                </button>
                {point.example_reviews.length ? (
                  <div className={`mt-3 space-y-2 ${expanded ? "" : "hidden"}`}>
                    {point.example_reviews.map((review, index) => (
                      <blockquote key={`${point.id}-${index}`} className="rounded-lg border-l-2 border-indigo/40 bg-field px-3 py-2 text-xs leading-5 text-muted">
                        “{review}”
                      </blockquote>
                    ))}
                  </div>
                ) : null}
                {point.evidence_urls.length ? (
                  <div className={`mt-3 flex flex-wrap gap-2 ${expanded ? "" : "hidden"}`}>
                    {point.evidence_urls.map((url, index) => (
                      <a
                        key={url}
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 py-1.5 text-xs font-semibold text-indigo transition hover:border-indigo/30 hover:bg-field"
                      >
                        <ExternalLink size={13} />
                        查看证据 {index + 1}
                      </a>
                    ))}
                  </div>
                ) : (
                  expanded ? <p className="mt-3 text-xs text-muted/75">当前为跨来源推导信号，暂无直接评论链接。</p> : null
                )}
              </div>
              );
            })}
          </div>
        </Section>

        <Section title="创新方向">
          <div className="space-y-3">
            {detail.innovation_ideas.slice(0, 6).map((idea) => {
              const expanded = selectedIdeaId === idea.id;
              return (
              <button
                key={idea.id}
                type="button"
                aria-expanded={expanded}
                onClick={() => setExpandedIdeaId((current) => (current === idea.id ? "" : idea.id))}
                className={`focus-ring w-full rounded-xl border bg-white p-4 text-left shadow-sm transition hover:border-indigo/30 hover:shadow-panel ${
                  expanded ? "border-indigo/30 shadow-panel" : "border-line"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-ink">{idea.idea_title}</p>
                    <p className={`mt-2 text-sm leading-6 text-muted ${expanded ? "" : "line-clamp-3"}`}>{idea.idea_description}</p>
                  </div>
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="electric-text text-lg font-semibold">{idea.differentiation_score}</span>
                    <ChevronDown size={15} className={`text-indigo transition-transform ${expanded ? "rotate-180" : ""}`} />
                  </span>
                </div>
                {expanded ? (
                  <div className="mt-3 grid gap-3 rounded-lg bg-field px-3 py-3 text-xs leading-5 text-muted md:grid-cols-2">
                    <div>
                      <p className="font-semibold text-ink">目标用户</p>
                      <p className="mt-1">{idea.target_user}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-ink">实施影响</p>
                      <p className="mt-1">市场 {idea.market_value_score} · 难度 {idea.difficulty_score} · 成本 {idea.cost_impact}</p>
                    </div>
                    <div className="md:col-span-2">
                      <p className="font-semibold text-ink">建议功能</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {idea.suggested_features.map((feature) => (
                          <span key={feature} className="rounded-md bg-white px-2 py-1 font-semibold text-muted">
                            {feature}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : null}
                <span className="mt-3 inline-flex text-xs font-semibold text-indigo">
                  {expanded ? "收起创新细节" : "展开创新细节"}
                </span>
              </button>
              );
            })}
          </div>
        </Section>
      </div>

      <div className="mt-6">
        <Section
          title="报告下载"
          action={<span className="rounded-lg bg-field px-3 py-1.5 text-sm font-semibold text-muted">4 种格式</span>}
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {downloadFormats.map(([format, label]) => (
              <a
                key={format}
                href={`${API_BASE_URL}/api/reports/${detail.report_id}/download?format=${format}`}
                className="focus-ring flex items-center justify-between rounded-xl border border-line bg-white px-4 py-3 text-sm font-semibold text-ink shadow-sm transition hover:border-indigo/30 hover:bg-field"
              >
                <span className="inline-flex items-center gap-2">
                  <Download size={16} className="text-indigo" />
                  {label}
                </span>
                <ExternalLink size={14} className="text-muted" />
              </a>
            ))}
          </div>
        </Section>
      </div>
    </AppShell>
  );
}
