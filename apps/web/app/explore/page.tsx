"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, CheckCircle2, CircleDashed, Clock3, FileText, Loader2, Plug, Search, Sparkles, Workflow } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { EmptyState, MetricCard, Section } from "@/components/ui";
import { api, type Opportunity, type SearchTask } from "@/lib/api";
import { useAuth } from "@/components/auth-provider";

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

const pipelineSteps = [
  "keyword_expanding",
  "collecting_trends",
  "collecting_patents",
  "collecting_competitors",
  "collecting_reviews",
  "collecting_supply_chain",
  "analyzing",
  "scoring",
  "generating_report",
  "completed",
];

function ExploreContent() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, refresh: refreshAuth } = useAuth();
  const [keyword, setKeyword] = useState(params.get("keyword") ?? "pet water fountain");
  const [industry, setIndustry] = useState("Consumer Product");
  const [targetMarket, setTargetMarket] = useState("United States");
  const [language, setLanguage] = useState("zh-CN");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [tasks, setTasks] = useState<SearchTask[]>([]);
  const [activeTask, setActiveTask] = useState<SearchTask | null>(null);

  useEffect(() => {
    if (!user) return;
    refreshWorkspace();
  }, [user]);

  async function refreshWorkspace() {
    const [opportunityRows, taskRows] = await Promise.all([
      api.listOpportunities().catch(() => []),
      api.listTasks().catch(() => []),
    ]);
    setOpportunities(opportunityRows);
    setTasks(taskRows);
  }

  async function waitForTask(taskId: string) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const task = await api.getTask(taskId);
      setActiveTask(task);
      setStatus(`${statusLabels[task.current_step] ?? task.current_step} · ${task.progress}%`);
      if (task.status === "completed") return task;
      if (task.status === "failed") {
        throw new Error(task.error_message || "分析任务失败");
      }
      if (task.status === "cancelled") {
        throw new Error("分析任务已取消");
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    throw new Error("分析任务超时，请在最近任务中查看结果。");
  }

  async function cancelTask(taskId: string) {
    setError("");
    try {
      const nextTask = await api.cancelTask(taskId);
      setActiveTask(nextTask);
      setStatus("任务已取消");
      await refreshWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "取消任务失败");
    }
  }

  async function retryTask(taskId: string) {
    setLoading(true);
    setError("");
    try {
      const created = await api.retryTask(taskId);
      await refreshAuth();
      setStatus("重试任务已进入后台队列");
      const task = await waitForTask(created.task_id);
      const opportunityId = task.opportunity_id ?? created.opportunity_id;
      if (!opportunityId) {
        throw new Error("任务完成但未返回机会 ID");
      }
      router.push(`/opportunities/${opportunityId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重试任务失败");
    } finally {
      await refreshWorkspace();
      setLoading(false);
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setStatus("创建搜索任务");
    try {
      const created = await api.createSearch({
        keyword,
        industry,
        target_market: targetMarket,
        language,
      });
      await refreshAuth();
      setStatus("任务已进入后台队列");
      const task = await waitForTask(created.task_id);
      const opportunityId = task.opportunity_id ?? created.opportunity_id;
      if (!opportunityId) {
        throw new Error("任务完成但未返回机会 ID");
      }
      setStatus("分析完成，正在打开详情页");
      router.push(`/opportunities/${opportunityId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "搜索失败");
      setStatus("");
    } finally {
      refreshWorkspace();
      setLoading(false);
    }
  }

  const visibleTask = activeTask ?? tasks[0];
  const currentStepIndex = visibleTask ? Math.max(0, pipelineSteps.indexOf(visibleTask.current_step)) : -1;

  return (
    <AppShell>
      <div className="mb-8 rounded-2xl border border-line/80 bg-white p-7 shadow-panel">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div>
            <div className="mb-4 inline-flex items-center gap-2 rounded-lg border border-ink/[0.06] bg-field/70 px-3 py-2 text-sm font-medium text-muted">
              <Sparkles size={16} className="text-indigo" />
              Opportunity Discovery
            </div>
            <h1 className="text-4xl font-semibold tracking-normal text-ink md:text-5xl">机会探索</h1>
            <p className="mt-3 max-w-2xl text-base leading-8 text-muted">
              输入产品关键词，系统会快速生成趋势、专利、竞品、痛点、供应链和创新方向的机会报告。
            </p>
          </div>
          <div className="rounded-xl bg-field px-4 py-3 text-sm text-muted">
            推荐测试：pet water fountain / 宠物饮水机 / camping lantern
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.08fr_0.92fr]">
        <Section title="生成新报告">
          <form onSubmit={submit} className="space-y-5">
            <label className="block">
              <span className="text-sm font-semibold text-ink/80">产品关键词</span>
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                className="focus-ring mt-2 w-full rounded-xl border border-line bg-white px-4 py-4 text-ink shadow-sm transition placeholder:text-muted/70 hover:border-indigo/30"
                placeholder="例如：pet water fountain / 宠物饮水机"
                required
              />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-sm font-semibold text-ink/80">行业</span>
                <input
                  value={industry}
                  onChange={(event) => setIndustry(event.target.value)}
                  className="focus-ring mt-2 w-full rounded-xl border border-line bg-white px-4 py-4 text-ink shadow-sm transition hover:border-indigo/30"
                />
              </label>
              <label className="block">
                <span className="text-sm font-semibold text-ink/80">目标市场</span>
                <select
                  value={targetMarket}
                  onChange={(event) => setTargetMarket(event.target.value)}
                  className="focus-ring mt-2 w-full rounded-xl border border-line bg-white px-4 py-4 text-ink shadow-sm transition hover:border-indigo/30"
                >
                  <option>United States</option>
                  <option>Germany</option>
                  <option>United Kingdom</option>
                  <option>Japan</option>
                  <option>China</option>
                </select>
              </label>
            </div>
            <label className="block">
              <span className="text-sm font-semibold text-ink/80">报告语言</span>
              <select
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
                className="focus-ring mt-2 w-full rounded-xl border border-line bg-white px-4 py-4 text-ink shadow-sm transition hover:border-indigo/30"
              >
                <option value="zh-CN">中文</option>
                <option value="en-US">English</option>
              </select>
            </label>
            <button
              type="submit"
              disabled={loading}
              className="focus-ring inline-flex w-full items-center justify-center gap-3 rounded-xl bg-gradient-to-br from-indigo to-violet px-5 py-4 font-semibold text-white shadow-glow transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? <Loader2 className="animate-spin" size={18} /> : <Search size={18} />}
              生成机会报告
            </button>
            {status ? <p className="text-sm text-signal">{status}</p> : null}
            {error ? <p className="rounded-md bg-clay/10 p-3 text-sm text-clay">{error}</p> : null}
          </form>
        </Section>

        <div className="grid gap-5 sm:grid-cols-3 lg:grid-cols-1">
          <MetricCard label="分析链路" value="P0" detail="搜索、分析、评分、报告、详情页已接通" icon={Workflow} />
          <MetricCard label="目标耗时" value="<60s" detail="真实数据源采集，慢源会降级为空结果" icon={Clock3} />
          <MetricCard label="数据源" value="API" detail="爬虫和 AI 模块保持可替换接口" icon={Plug} />
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <Section
          title="当前生成状态"
          action={
            visibleTask ? (
              <span className="rounded-lg bg-field px-3 py-1.5 text-sm font-semibold text-muted">
                {visibleTask.progress}%
              </span>
            ) : null
          }
        >
          {!visibleTask ? (
            <EmptyState title="暂无生成任务" description="从上方输入关键词后，这里会显示完整分析进度。" />
          ) : (
            <div className="space-y-5">
              <div className="flex flex-col justify-between gap-3 rounded-xl bg-field/70 p-4 sm:flex-row sm:items-center">
                <div>
                  <p className="text-sm font-semibold text-muted">关键词</p>
                  <p className="mt-1 text-lg font-semibold text-ink">{visibleTask.keyword}</p>
                </div>
                <span className="inline-flex w-fit items-center gap-2 rounded-full bg-white px-3 py-2 text-sm font-semibold text-indigo shadow-sm">
                  {visibleTask.status === "completed" ? <CheckCircle2 size={16} /> : <CircleDashed size={16} />}
                  {statusLabels[visibleTask.status] ?? visibleTask.status}
                </span>
              </div>
              {visibleTask.status !== "completed" && visibleTask.status !== "failed" && visibleTask.status !== "cancelled" ? (
                <button
                  type="button"
                  onClick={() => cancelTask(visibleTask.id)}
                  className="focus-ring rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink shadow-sm transition hover:border-clay/40"
                >
                  取消任务
                </button>
              ) : null}
              {visibleTask.status === "failed" || visibleTask.status === "cancelled" ? (
                <button
                  type="button"
                  onClick={() => retryTask(visibleTask.id)}
                  className="focus-ring rounded-lg bg-gradient-to-br from-indigo to-violet px-3 py-2 text-sm font-semibold text-white shadow-glow"
                >
                  重试任务
                </button>
              ) : null}
              <div className="h-2 overflow-hidden rounded-full bg-ink/10">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo to-violet transition-all"
                  style={{ width: `${Math.max(0, Math.min(100, visibleTask.progress))}%` }}
                />
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {pipelineSteps.map((step, index) => {
                  const done = visibleTask.status === "completed" || index <= currentStepIndex;
                  return (
                    <div key={step} className={`rounded-lg border px-3 py-2 text-sm ${done ? "border-indigo/20 bg-indigo/5 text-ink" : "border-line bg-white text-muted"}`}>
                      <span className="mr-2 font-semibold text-indigo">{String(index + 1).padStart(2, "0")}</span>
                      {statusLabels[step]}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Section>

        <Section title="最近任务">
          {tasks.length === 0 ? (
            <EmptyState title="还没有搜索任务" description="每次生成报告都会沉淀为一条可追踪任务。" />
          ) : (
            <div className="space-y-3">
              {tasks.slice(0, 5).map((task) => (
                <article key={task.id} className="rounded-xl border border-line bg-white p-4 shadow-sm">
                  <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-ink">{task.keyword}</p>
                        <span className="rounded-md bg-field px-2 py-1 text-xs font-semibold text-muted">{task.target_market}</span>
                        <span className="rounded-md bg-indigo/10 px-2 py-1 text-xs font-semibold text-indigo">{statusLabels[task.status] ?? task.status}</span>
                      </div>
                      <p className="mt-2 text-sm text-muted">{new Date(task.created_at).toLocaleString()}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {task.opportunity_id ? (
                        <button
                          onClick={() => router.push(`/opportunities/${task.opportunity_id}`)}
                          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink hover:bg-field"
                        >
                          机会 <ArrowRight size={14} />
                        </button>
                      ) : null}
                      {task.status !== "completed" && task.status !== "failed" && task.status !== "cancelled" ? (
                        <button
                          onClick={() => cancelTask(task.id)}
                          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink hover:bg-field"
                        >
                          取消
                        </button>
                      ) : null}
                      {task.status === "failed" || task.status === "cancelled" ? (
                        <button
                          onClick={() => retryTask(task.id)}
                          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-ink hover:bg-field"
                        >
                          重试
                        </button>
                      ) : null}
                      {task.report_id ? (
                        <button
                          onClick={() => router.push(`/reports/${task.report_id}`)}
                          className="focus-ring inline-flex items-center gap-2 rounded-lg bg-gradient-to-br from-indigo to-violet px-3 py-2 text-sm font-semibold text-white shadow-glow"
                        >
                          报告 <FileText size={14} />
                        </button>
                      ) : null}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Section>
      </div>

      <div className="mt-6">
        <Section title="最近机会">
          {opportunities.length === 0 ? (
            <EmptyState title="还没有机会记录" description="生成一次报告后，机会会出现在这里。" />
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {opportunities.map((item) => (
                <button
                  key={item.id}
                  onClick={() => router.push(`/opportunities/${item.id}`)}
                  className="group rounded-xl border border-line bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-indigo/30 hover:shadow-panel"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-ink">{item.product_name}</p>
                      <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted">{item.short_description}</p>
                    </div>
                    <span className="electric-text text-2xl font-semibold">{item.opportunity_score}</span>
                  </div>
                  <span className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-indigo">
                    查看详情 <ArrowRight size={15} className="transition group-hover:translate-x-0.5" />
                  </span>
                </button>
              ))}
            </div>
          )}
        </Section>
      </div>
    </AppShell>
  );
}

export default function ExplorePage() {
  return (
    <Suspense fallback={<AppShell><Section title="机会探索"><p className="text-muted">加载中...</p></Section></AppShell>}>
      <ExploreContent />
    </Suspense>
  );
}
