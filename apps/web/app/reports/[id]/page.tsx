"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertCircle, ArrowLeft, CalendarClock, CheckCircle2, Clock3, Database, Download, ExternalLink, FileDown, FileText, Gauge, Layers3, Loader2, RefreshCw, Search, Settings, Sparkles, Workflow } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { EmptyState, MetricCard, Section } from "@/components/ui";
import { API_BASE_URL, api, type Report } from "@/lib/api";

const reportSections = [
  ["executive", "执行摘要", "executive_summary"],
  ["market", "市场分析", "market_analysis"],
  ["trend", "趋势分析", "trend_analysis"],
  ["patent", "专利分析", "patent_analysis"],
  ["competitor", "竞品分析", "competitor_analysis"],
  ["pain", "用户痛点", "pain_point_analysis"],
  ["supply", "供应链分析", "supply_chain_analysis"],
  ["innovation", "创新建议", "innovation_analysis"],
  ["quality", "数据来源与可信度", "data_quality_summary"],
  ["recommendation", "最终建议", "final_recommendation"],
] as const;

const downloadFormats = [
  ["markdown", "Markdown", "MD"],
  ["pdf", "PDF", "PDF"],
  ["excel", "Excel", "XLSX"],
  ["word", "Word", "DOCX"],
] as const;

function scoreLabel(score: number) {
  if (score >= 80) return "强机会";
  if (score >= 65) return "观察推进";
  return "谨慎验证";
}

function agentStatusLabel(status: string) {
  const labels: Record<string, string> = {
    completed: "完整完成",
    completed_with_gaps: "部分完成",
    missing_credentials: "未配置",
    provider_error: "调用失败",
  };
  return labels[status] ?? status;
}

function confidenceLabel(level?: string) {
  if (level === "high") return "高可信";
  if (level === "medium") return "中可信";
  if (level === "low") return "低可信";
  return "待评估";
}

function sourceStatusLabel(status: string) {
  const labels: Record<string, string> = {
    ok: "可用",
    empty: "无结果",
    guarded: "需授权",
    missing_credentials: "未配置",
    missing_session: "需登录",
    provider_error: "调用失败",
    not_recorded: "未记录",
  };
  return labels[status] ?? status;
}

function sourceStatusTone(status: string) {
  if (status === "ok" || status === "configured") return "bg-indigo/10 text-indigo";
  if (status === "guarded" || status === "missing_credentials" || status === "missing_session") return "bg-amber-50 text-amber-700";
  return "bg-clay/10 text-clay";
}

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const { user } = useAuth();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError("");
    api
      .getReport(params.id)
      .then(setReport)
      .catch((err) => setError(err instanceof Error ? err.message : "报告加载失败"))
      .finally(() => setLoading(false));
  }, [params.id, user]);

  if (loading) {
    return (
      <AppShell>
        <Section title="报告详情">
          <div className="flex items-center gap-2 text-muted">
            <Loader2 className="animate-spin" size={18} />
            正在加载报告...
          </div>
        </Section>
      </AppShell>
    );
  }

  if (error || !report) {
    return (
      <AppShell>
        <EmptyState title="未找到报告" description={error || "请回到报告中心重新打开。"} />
      </AppShell>
    );
  }

  const createdAt = new Date(report.created_at);
  const sectionCount = reportSections.length;
  const scoreTone =
    report.report_score >= 80
      ? "border-indigo/20 bg-indigo/10 text-indigo"
      : report.report_score >= 65
        ? "border-violet/20 bg-[#F4F0FF] text-violet"
        : "border-clay/20 bg-clay/10 text-clay";
  const dataQuality = report.data_quality;
  const hasDataQuality = typeof dataQuality?.confidence_score === "number";
  const sourceCoverage = dataQuality?.sources ?? [];
  const actionableSources = sourceCoverage.filter((source) => source.status !== "ok" && source.status !== "configured");
  const remediationActions = actionableSources.slice(0, 4).map((source) => {
    if (source.key === "1688") {
      return {
        key: source.key,
        title: "连接 1688 会话",
        description: "补齐国内供应商、MOQ 与报价证据；连接后建议重新分析同一关键词。",
        href: "/settings",
        label: "去设置",
        icon: Settings,
      };
    }
    if (source.key === "llm_agent") {
      return {
        key: source.key,
        title: user?.role === "admin" ? "检查 AI API 配置" : "联系管理员启用 AI",
        description: "Agent 未完整完成时，报告会使用规则降级；配置可用模型后再重新生成。",
        href: user?.role === "admin" ? "/admin" : "/settings",
        label: user?.role === "admin" ? "去后台" : "查看设置",
        icon: Sparkles,
      };
    }
    return {
      key: source.key,
      title: `补采 ${source.label}`,
      description: `${source.category}证据当前不足；建议重新分析关键词，或更换更具体的产品词。`,
      href: "/",
      label: "重新分析",
      icon: Search,
    };
  });
  const visibleGaps = dataQuality?.gaps?.slice(0, 3) ?? [];

  async function refreshCurrentReport(reportId: string) {
    setRefreshing(true);
    setError("");
    try {
      setReport(await api.refreshReport(reportId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "报告刷新失败");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <AppShell>
      <div className="mb-6 overflow-hidden rounded-2xl border border-line/80 bg-white shadow-panel">
        <div className="relative p-7 lg:p-8">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_10%,rgba(91,92,246,0.10),transparent_34%),linear-gradient(135deg,rgba(255,255,255,0.98),rgba(250,250,252,0.86))]" />
          <div className="relative flex flex-col justify-between gap-6 lg:flex-row">
            <div>
              <Link href="/reports" className="focus-ring mb-4 inline-flex items-center gap-2 text-sm font-semibold text-muted hover:text-ink">
                <ArrowLeft size={16} />
                返回报告中心
              </Link>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-3 py-1.5 text-xs font-bold ${scoreTone}`}>{scoreLabel(report.report_score)}</span>
                <span className="rounded-full border border-line bg-white/70 px-3 py-1.5 text-xs font-semibold text-muted">{report.status}</span>
              </div>
              <h1 className="max-w-4xl text-3xl font-semibold tracking-normal text-ink md:text-5xl">{report.report_title}</h1>
              <p className="mt-4 max-w-3xl text-base leading-8 text-muted">{report.executive_summary}</p>
              {error ? <p className="mt-3 rounded-lg border border-clay/20 bg-clay/10 px-3 py-2 text-sm text-clay">{error}</p> : null}
            </div>

            <div className="flex shrink-0 flex-col gap-3 lg:w-[17rem]">
              <button
                type="button"
                onClick={() => refreshCurrentReport(report.id)}
                disabled={refreshing}
                className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-white/80 px-4 py-3 text-sm font-semibold text-ink shadow-sm transition hover:bg-field disabled:opacity-60"
              >
                <RefreshCw size={16} className={refreshing ? "animate-spin text-indigo" : "text-indigo"} />
                {refreshing ? "刷新中" : "刷新报告"}
              </button>
              <Link
                href={`/opportunities/${report.opportunity_id}`}
                className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-br from-indigo to-violet px-4 py-3 text-sm font-semibold text-white shadow-glow"
              >
                <ExternalLink size={16} />
                机会详情
              </Link>
              <div className="grid grid-cols-2 gap-2">
                {downloadFormats.map(([format, label]) => (
                  <a
                    key={format}
                    href={`${API_BASE_URL}/api/reports/${report.id}/download?format=${format}`}
                    className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-white/80 px-3 py-3 text-sm font-semibold text-ink transition hover:bg-field"
                  >
                    <Download size={15} />
                    {label}
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mb-6 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="报告评分" value={report.report_score} detail={scoreLabel(report.report_score)} icon={Gauge} />
        <MetricCard label="报告章节" value={sectionCount} detail="结构化分析段落" icon={Layers3} />
        <MetricCard label="导出格式" value="4" detail="MD / PDF / Excel / Word" icon={FileDown} />
        <MetricCard label="生成时间" value={createdAt.toLocaleDateString()} detail={createdAt.toLocaleTimeString()} icon={CalendarClock} />
      </div>

      {hasDataQuality && dataQuality ? (
        <div className="mb-6 rounded-2xl border border-line bg-white p-6 shadow-panel">
          <div className="mb-5 flex flex-col justify-between gap-4 lg:flex-row lg:items-start">
            <div>
              <p className="text-sm font-semibold text-muted">数据可信度</p>
              <h2 className="mt-1 text-2xl font-semibold text-ink">
                {dataQuality.confidence_score}/100 · {confidenceLabel(dataQuality.confidence_level)}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">
                这里显示真实数据源覆盖情况和可补强动作；不会把内部采集失败日志直接暴露为结论。
              </p>
            </div>
            <button
              type="button"
              onClick={() => refreshCurrentReport(report.id)}
              disabled={refreshing}
              className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-white px-4 py-3 text-sm font-semibold text-ink shadow-sm transition hover:bg-field disabled:opacity-60"
            >
              <RefreshCw size={16} className={refreshing ? "animate-spin text-indigo" : "text-indigo"} />
              刷新结构化摘要
            </button>
          </div>

          <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <div className="rounded-xl bg-field p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                <Database size={16} className="text-indigo" />
                来源覆盖
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {sourceCoverage.map((source) => (
                  <div key={source.key} className="rounded-lg border border-line bg-white px-3 py-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-ink">{source.label}</span>
                        <span className="mt-0.5 block text-xs text-muted">{source.category} · {source.count} signals</span>
                      </span>
                      <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-bold ${sourceStatusTone(source.status)}`}>
                        {sourceStatusLabel(source.status)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-line bg-white p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                <AlertCircle size={16} className="text-indigo" />
                建议动作
              </div>
              {remediationActions.length ? (
                <div className="grid gap-3">
                  {remediationActions.map((action) => {
                    const Icon = action.icon;
                    return (
                      <div key={action.key} className="flex flex-col gap-3 rounded-lg bg-field px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-start gap-3">
                          <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-indigo/10 text-indigo">
                            <Icon size={17} />
                          </span>
                          <span>
                            <span className="block text-sm font-semibold text-ink">{action.title}</span>
                            <span className="mt-1 block text-xs leading-5 text-muted">{action.description}</span>
                          </span>
                        </div>
                        <Link
                          href={action.href}
                          className="focus-ring inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-indigo px-3 py-2 text-xs font-semibold text-white"
                        >
                          {action.label}
                          <ExternalLink size={13} />
                        </Link>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="rounded-lg bg-indigo/10 px-3 py-4 text-sm font-semibold text-indigo">
                  主要数据源已覆盖，本报告可进入下一步人工复核或小额验证。
                </p>
              )}
              {visibleGaps.length ? (
                <div className="mt-4 border-t border-line pt-3">
                  <p className="mb-2 text-xs font-semibold text-muted">当前限制</p>
                  <div className="space-y-2">
                    {visibleGaps.map((gap) => (
                      <p key={gap} className="rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                        {gap}
                      </p>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {report.agent_run?.id ? (
        <div className="mb-6">
          <Section
            title="AI Agent 编排"
            action={
              <span className={`rounded-full border px-3 py-1.5 text-xs font-bold ${
                report.agent_run.status === "completed"
                  ? "border-indigo/20 bg-indigo/10 text-indigo"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}>
                {agentStatusLabel(report.agent_run.status)}
              </span>
            }
          >
            <div className="grid gap-4 border-b border-line pb-5 md:grid-cols-4">
              <div>
                <p className="text-xs font-semibold text-muted">模型</p>
                <p className="mt-2 font-semibold text-ink">{report.agent_run.provider ?? "规则降级"}</p>
                <p className="mt-1 truncate text-xs text-muted">{report.agent_run.model ?? "未调用模型"}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-muted">执行耗时</p>
                <p className="mt-2 font-semibold text-ink">{(report.agent_run.duration_ms / 1000).toFixed(1)} 秒</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-muted">Token</p>
                <p className="mt-2 font-semibold text-ink">{(report.agent_run.input_tokens + report.agent_run.output_tokens).toLocaleString()}</p>
                <p className="mt-1 text-xs text-muted">输入 {report.agent_run.input_tokens.toLocaleString()} / 输出 {report.agent_run.output_tokens.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-muted">运行 ID</p>
                <p className="mt-2 truncate font-mono text-xs font-semibold text-ink">{report.agent_run.id}</p>
                {report.agent_run.estimated_cost_usd != null ? (
                  <p className="mt-1 text-xs text-muted">估算 ${report.agent_run.estimated_cost_usd.toFixed(4)}</p>
                ) : null}
              </div>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              {report.agent_run.steps.map((step, index) => (
                <div key={`${step.name}-${index}`} className="border-l-2 border-indigo/25 pl-4">
                  <div className="flex items-start justify-between gap-2">
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-indigo/10 text-indigo">
                      {step.name === "scoring_report" ? <Workflow size={15} /> : <Sparkles size={15} />}
                    </span>
                    <span className={`text-[11px] font-bold ${step.status === "completed" ? "text-indigo" : step.status === "skipped" ? "text-muted" : "text-clay"}`}>
                      {step.status === "completed" ? "DONE" : step.status.toUpperCase()}
                    </span>
                  </div>
                  <p className="mt-3 text-sm font-semibold text-ink">{step.label}</p>
                  <p className="mt-2 flex items-center gap-1 text-xs text-muted">
                    <Clock3 size={12} />
                    {(step.duration_ms / 1000).toFixed(1)}s · {step.input_tokens + step.output_tokens} tokens
                  </p>
                  {step.error ? <p className="mt-2 line-clamp-2 text-xs leading-5 text-clay">{step.error}</p> : null}
                </div>
              ))}
            </div>
            {report.agent_run.score_reasoning ? (
              <p className="mt-5 border-t border-line pt-4 text-sm leading-7 text-muted">
                <span className="font-semibold text-ink">评分解释：</span>
                {report.agent_run.score_reasoning}
              </p>
            ) : null}
          </Section>
        </div>
      ) : null}

      <div className="mb-6 grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-2xl border border-line/80 bg-white p-6 shadow-panel">
          <div className="mb-5 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-muted">核心结论</p>
              <h2 className="mt-1 text-xl font-semibold text-ink">先读这三条，再进入完整报告</h2>
            </div>
            <Sparkles className="text-indigo" size={22} />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {[
              ["机会判断", report.executive_summary],
              ["差异化方向", report.innovation_analysis],
              ["最终建议", report.final_recommendation],
            ].map(([label, content]) => (
              <div key={label} className="rounded-xl border border-line bg-gradient-to-br from-white to-field/70 p-4">
                <p className="mb-3 inline-flex items-center gap-2 rounded-full bg-indigo/10 px-2.5 py-1 text-xs font-bold text-indigo">
                  <CheckCircle2 size={13} />
                  {label}
                </p>
                <p className="line-clamp-5 text-sm leading-6 text-muted">{content}</p>
              </div>
            ))}
          </div>
        </section>

        <Section title="导出报告">
          <div className="grid gap-3 sm:grid-cols-2">
            {downloadFormats.map(([format, label, shortLabel]) => (
              <a
                key={format}
                href={`${API_BASE_URL}/api/reports/${report.id}/download?format=${format}`}
                className="focus-ring flex items-center justify-between rounded-xl border border-line bg-white p-4 shadow-sm transition hover:border-indigo/30 hover:bg-field"
              >
                <span>
                  <span className="block text-sm font-semibold text-ink">{label}</span>
                  <span className="mt-1 block text-xs text-muted">{shortLabel} 文件下载</span>
                </span>
                <Download size={17} className="text-indigo" />
              </a>
            ))}
          </div>
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-[0.7fr_1.3fr]">
        <div className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <Section title="目录">
            <div className="space-y-2">
              {reportSections.map(([id, label], index) => (
                <a key={id} href={`#${id}`} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-semibold text-muted transition hover:bg-field hover:text-ink">
                  <span className="grid size-6 place-items-center rounded-full bg-field text-[11px] text-muted">{index + 1}</span>
                  {label}
                </a>
              ))}
            </div>
          </Section>

          <Section title="报告信息">
            <div className="space-y-3 text-sm text-muted">
              <p className="flex items-center justify-between gap-3">
                <span>状态</span>
                <span className="font-semibold text-ink">{report.status}</span>
              </p>
              <p className="flex items-center justify-between gap-3">
                <span>评分</span>
                <span className="font-semibold text-ink">{report.report_score}/100</span>
              </p>
              <p className="flex items-center justify-between gap-3">
                <span>生成</span>
                <span className="font-semibold text-ink">{createdAt.toLocaleString()}</span>
              </p>
            </div>
          </Section>
        </div>

        <div className="space-y-6">
          {reportSections.map(([id, label, key], index) => (
            <section key={id} id={id} className="scroll-mt-28 rounded-2xl border border-line bg-white p-6 shadow-panel">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-indigo">
                  SECTION {String(index + 1).padStart(2, "0")}
                </p>
                <FileText size={17} className="text-muted" />
              </div>
              <h2 className="mt-3 text-2xl font-semibold text-ink">{label}</h2>
              <p className="mt-4 whitespace-pre-wrap text-base leading-8 text-muted">{report[key] || "旧报告未记录该结构化字段；请重新生成报告以获得完整来源可信度摘要。"}</p>
            </section>
          ))}

          <section className="rounded-2xl border border-line bg-white p-6 shadow-panel">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-indigo">MARKDOWN</p>
                <h2 className="mt-2 text-2xl font-semibold text-ink">完整 Markdown 源文</h2>
              </div>
              <a
                href={`${API_BASE_URL}/api/reports/${report.id}/download?format=markdown`}
                className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink hover:bg-field"
              >
                <Download size={16} />
                下载
              </a>
            </div>
            <pre className="max-h-[520px] overflow-auto rounded-xl border border-line bg-field p-5 text-sm leading-7 text-ink/80 whitespace-pre-wrap">
              {report.markdown_content}
            </pre>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
