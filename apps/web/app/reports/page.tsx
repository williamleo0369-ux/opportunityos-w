"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, ArrowDownUp, CheckCircle2, CircleDashed, Download, FileText, Gauge, Loader2, Search, SlidersHorizontal } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { EmptyState, MetricCard, Section } from "@/components/ui";
import { API_BASE_URL, api, type Report, type SearchTask } from "@/lib/api";

const downloadFormats = [
  ["markdown", "MD"],
  ["pdf", "PDF"],
  ["excel", "Excel"],
  ["word", "Word"],
] as const;

const statusLabels: Record<string, string> = {
  pending: "排队中",
  keyword_expanding: "关键词扩展",
  collecting_trends: "趋势采集",
  collecting_patents: "专利扫描",
  collecting_competitors: "竞品采集",
  collecting_reviews: "痛点洞察",
  collecting_supply_chain: "供应链检查",
  analyzing: "综合分析",
  scoring: "机会评分",
  generating_report: "报告生成",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export default function ReportsPage() {
  const { user } = useAuth();
  const [reports, setReports] = useState<Report[]>([]);
  const [tasks, setTasks] = useState<SearchTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [scoreFilter, setScoreFilter] = useState<"all" | "strong" | "watch" | "risky">("all");
  const [sortBy, setSortBy] = useState<"newest" | "score">("newest");

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    Promise.all([api.listReports().catch(() => []), api.listTasks().catch(() => [])])
      .then(([reportRows, taskRows]) => {
        setReports(reportRows);
        setTasks(taskRows);
      })
      .finally(() => setLoading(false));
  }, [user]);

  const filteredReports = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return reports
      .filter((report) => {
        const matchesQuery =
          normalizedQuery.length === 0 ||
          report.report_title.toLowerCase().includes(normalizedQuery) ||
          report.executive_summary.toLowerCase().includes(normalizedQuery) ||
          report.final_recommendation.toLowerCase().includes(normalizedQuery);
        const matchesScore =
          scoreFilter === "all" ||
          (scoreFilter === "strong" && report.report_score >= 80) ||
          (scoreFilter === "watch" && report.report_score >= 65 && report.report_score < 80) ||
          (scoreFilter === "risky" && report.report_score < 65);
        return matchesQuery && matchesScore;
      })
      .sort((a, b) => {
        if (sortBy === "score") {
          return b.report_score - a.report_score;
        }
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      });
  }, [query, reports, scoreFilter, sortBy]);

  const strongCount = reports.filter((report) => report.report_score >= 80).length;
  const watchCount = reports.filter((report) => report.report_score >= 65 && report.report_score < 80).length;
  const riskyCount = reports.filter((report) => report.report_score < 65).length;
  const taskById = useMemo(() => new Map(tasks.map((task) => [task.id, task])), [tasks]);
  const completedTasks = tasks.filter((task) => task.status === "completed").length;
  const runningTasks = tasks.filter((task) => task.status !== "completed" && task.status !== "failed").length;
  const failedTasks = tasks.filter((task) => task.status === "failed").length;

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-4xl font-semibold tracking-normal text-ink md:text-5xl">报告中心</h1>
        <p className="mt-3 max-w-2xl text-base leading-8 text-muted">沉淀每一次机会分析，快速回看评分、结论和可下载报告。</p>
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        <MetricCard label="报告总数" value={reports.length} detail="已启用本地持久化存储" icon={Archive} />
        <MetricCard label="可下载格式" value="4" detail="Markdown / PDF / Excel / Word" icon={Download} />
        <MetricCard label="平均分" value={reports.length ? Math.round(reports.reduce((sum, item) => sum + item.report_score, 0) / reports.length) : 0} detail="机会报告评分" icon={Gauge} />
      </div>

      <div className="mt-6">
        <Section
          title="生成状态看板"
          action={<span className="rounded-lg bg-field px-3 py-1.5 text-sm font-semibold text-muted">{tasks.length} 个任务</span>}
        >
          <div className="grid gap-3 md:grid-cols-4">
            {[
              ["已完成", completedTasks, "报告已经生成并可进入阅读视图"],
              ["处理中", runningTasks, "等待采集、分析或评分完成"],
              ["异常", failedTasks, "需要重试或检查任务错误"],
              ["可导出", reports.filter((report) => report.status === "completed").length, "支持 MD / PDF / Excel / Word"],
            ].map(([label, value, detail]) => (
              <div key={label} className="rounded-xl border border-line bg-white p-4 shadow-sm">
                <p className="text-sm font-semibold text-muted">{label}</p>
                <p className="electric-text mt-2 text-3xl font-semibold">{value}</p>
                <p className="mt-2 text-xs leading-5 text-muted">{detail}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 space-y-2">
            {tasks.slice(0, 4).map((task) => (
              <div key={task.id} className="rounded-xl border border-line/80 bg-field/50 p-3">
                <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                  <span className="flex min-w-0 items-center gap-2 font-semibold text-ink">
                    {task.status === "completed" ? <CheckCircle2 className="shrink-0 text-indigo" size={16} /> : <CircleDashed className="shrink-0 text-muted" size={16} />}
                    <span className="truncate">{task.keyword}</span>
                  </span>
                  <span className="shrink-0 text-muted">{statusLabels[task.status] ?? task.status}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-ink/10">
                  <div className="h-full rounded-full bg-gradient-to-r from-indigo to-violet" style={{ width: `${Math.max(0, Math.min(100, task.progress))}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>

      <div className="mt-6">
        <Section
          title="最近报告"
          action={
            <span className="rounded-lg bg-field px-3 py-1.5 text-sm font-semibold text-muted">
              {filteredReports.length} / {reports.length}
            </span>
          }
        >
          <div className="mb-5 grid gap-3 lg:grid-cols-[1fr_auto_auto]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" size={18} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="focus-ring w-full rounded-xl border border-line bg-white py-3 pl-11 pr-4 text-sm text-ink shadow-sm transition placeholder:text-muted/70 hover:border-indigo/30"
                placeholder="搜索报告、摘要或建议..."
              />
            </label>
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-white p-1 shadow-sm">
              {[
                ["all", "全部", reports.length],
                ["strong", "强机会", strongCount],
                ["watch", "观察", watchCount],
                ["risky", "谨慎", riskyCount],
              ].map(([value, label, count]) => (
                <button
                  key={value}
                  onClick={() => setScoreFilter(value as typeof scoreFilter)}
                  className={`focus-ring inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${
                    scoreFilter === value ? "bg-indigo text-white" : "text-muted hover:bg-field hover:text-ink"
                  }`}
                >
                  <SlidersHorizontal size={14} />
                  {label}
                  <span className={scoreFilter === value ? "text-white/75" : "text-muted/70"}>{count}</span>
                </button>
              ))}
            </div>
            <button
              onClick={() => setSortBy((current) => (current === "newest" ? "score" : "newest"))}
              className="focus-ring inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-white px-4 py-3 text-sm font-semibold text-ink shadow-sm transition hover:bg-field"
            >
              <ArrowDownUp size={16} />
              {sortBy === "newest" ? "最新优先" : "高分优先"}
            </button>
          </div>

          {loading ? (
            <div className="flex items-center gap-2 text-muted">
              <Loader2 className="animate-spin" size={18} />
              加载报告中...
            </div>
          ) : reports.length === 0 ? (
            <EmptyState title="还没有报告" description="从机会探索页生成一次报告后，这里会显示报告列表。" />
          ) : filteredReports.length === 0 ? (
            <EmptyState title="没有匹配的报告" description="换一个关键词，或切回全部评分区间。" />
          ) : (
            <div className="space-y-3">
              {filteredReports.map((report) => (
                <article id={report.id} key={report.id} className="rounded-xl border border-line bg-white p-5 shadow-sm transition hover:border-indigo/30 hover:shadow-panel">
                  <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
                    <div>
                      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-muted">
                        <FileText size={16} />
                        {new Date(report.created_at).toLocaleString()}
                        <span className="rounded-md bg-field px-2 py-1 text-xs font-semibold text-muted">{report.status}</span>
                        {taskById.get(report.search_task_id) ? (
                          <span className="rounded-md bg-indigo/10 px-2 py-1 text-xs font-semibold text-indigo">
                            {statusLabels[taskById.get(report.search_task_id)?.status ?? ""] ?? taskById.get(report.search_task_id)?.status}
                          </span>
                        ) : null}
                        {!report.data_quality_summary ? (
                          <span className="rounded-md bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700">待刷新来源</span>
                        ) : null}
                        <span
                          className={`rounded-md px-2 py-1 text-xs font-semibold ${
                            report.report_score >= 80
                              ? "bg-indigo/10 text-indigo"
                              : report.report_score >= 65
                                ? "bg-[#F4F0FF] text-violet"
                                : "bg-clay/10 text-clay"
                          }`}
                        >
                          {report.report_score >= 80 ? "强机会" : report.report_score >= 65 ? "观察名单" : "谨慎推进"}
                        </span>
                      </div>
                      <h2 className="text-xl font-semibold text-ink">{report.report_title}</h2>
                      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">{report.executive_summary}</p>
                      {taskById.get(report.search_task_id) ? (
                        <div className="mt-4 max-w-xl">
                          <div className="mb-1 flex items-center justify-between text-xs font-semibold text-muted">
                            <span>生成进度</span>
                            <span>{taskById.get(report.search_task_id)?.progress}%</span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded-full bg-ink/10">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-indigo to-violet"
                              style={{ width: `${Math.max(0, Math.min(100, taskById.get(report.search_task_id)?.progress ?? 0))}%` }}
                            />
                          </div>
                        </div>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className="electric-text px-3 py-2 text-2xl font-semibold">{report.report_score}</span>
                      <div className="flex flex-wrap gap-1">
                        {downloadFormats.map(([format, label]) => (
                          <a
                            key={format}
                            href={`${API_BASE_URL}/api/reports/${report.id}/download?format=${format}`}
                            className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 py-2 text-xs font-semibold text-ink hover:bg-field"
                          >
                            <Download size={14} />
                            {label}
                          </a>
                        ))}
                      </div>
                      <Link
                        href={`/reports/${report.id}`}
                        className="focus-ring rounded-lg bg-gradient-to-br from-indigo to-violet px-3 py-2 text-sm font-semibold text-white shadow-glow"
                      >
                        阅读
                      </Link>
                      <Link
                        href={`/opportunities/${report.opportunity_id}`}
                        className="focus-ring rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink hover:bg-field"
                      >
                        机会
                      </Link>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Section>
      </div>
    </AppShell>
  );
}
