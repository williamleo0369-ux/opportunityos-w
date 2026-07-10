"use client";

import { useEffect, useRef, useState } from "react";
import { Activity, CheckCircle2, Database, Download, FileArchive, FileSpreadsheet, Loader2, RefreshCw, Server, ShieldCheck, Trash2, Upload, UserRound } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { MetricCard, Section } from "@/components/ui";
import { api, type ApiLog, type SearchQueueStatus, type SourceHealth, type SourceHealthHistory, type SourceHealthSchedulerStatus, type SupplierCatalog, type SystemStatus } from "@/lib/api";

const formatBytes = (bytes: number) => {
  if (bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

const queueHealthLabel = (health?: string) => {
  if (health === "healthy") return "在线";
  if (health === "offline") return "离线";
  if (health === "degraded") return "需关注";
  return "未知";
};

const queueHealthClass = (health?: string) => {
  if (health === "healthy") return "bg-indigo/10 text-indigo";
  if (health === "offline") return "bg-clay/10 text-clay";
  return "bg-amber-50 text-amber-700";
};

export default function SettingsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [sourceHealth, setSourceHealth] = useState<SourceHealth | null>(null);
  const [sourceHealthHistory, setSourceHealthHistory] = useState<SourceHealthHistory>([]);
  const [sourceHealthScheduler, setSourceHealthScheduler] = useState<SourceHealthSchedulerStatus | null>(null);
  const [searchQueue, setSearchQueue] = useState<SearchQueueStatus | null>(null);
  const [supplierCatalog, setSupplierCatalog] = useState<SupplierCatalog | null>(null);
  const [apiLogs, setApiLogs] = useState<ApiLog[]>([]);
  const [supplierCsv, setSupplierCsv] = useState("");
  const [supplierFileName, setSupplierFileName] = useState("");
  const [confirmingCatalogClear, setConfirmingCatalogClear] = useState(false);
  const supplierFileInput = useRef<HTMLInputElement>(null);
  const [schedulerInterval, setSchedulerInterval] = useState(3600);
  const [loading, setLoading] = useState(true);
  const [refreshingSources, setRefreshingSources] = useState(false);
  const [refreshingQueue, setRefreshingQueue] = useState(false);
  const [schedulerBusy, setSchedulerBusy] = useState(false);
  const [supplierBusy, setSupplierBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError("");
    Promise.all([api.getSystemStatus(), api.getSourceHealthHistory(5), api.getSourceHealthScheduler(), api.getSearchQueueStatus(), api.listApiLogs(6), api.getSupplierCatalog()])
      .then(([nextStatus, nextHistory, nextScheduler, nextQueue, nextLogs, nextCatalog]) => {
        setStatus(nextStatus);
        setSourceHealth(nextStatus.pipeline?.source_health ?? null);
        setSourceHealthHistory(nextHistory);
        setSourceHealthScheduler(nextScheduler);
        setSearchQueue(nextQueue);
        setSupplierCatalog(nextCatalog);
        setApiLogs(nextLogs);
        if (nextScheduler.interval_seconds >= 60) {
          setSchedulerInterval(nextScheduler.interval_seconds);
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "系统状态读取失败"))
      .finally(() => setLoading(false));
  }, [user]);

  const syncSourceHealthHistory = async () => {
    const nextHistory = await api.getSourceHealthHistory(5);
    setSourceHealthHistory(nextHistory);
    setStatus((current) =>
      current
        ? {
            ...current,
            counts: {
              ...current.counts,
              source_health_checks: nextHistory.length,
            },
          }
        : current,
    );
    return nextHistory;
  };

  const refreshSearchQueue = async () => {
    setRefreshingQueue(true);
    try {
      const nextQueue = await api.getSearchQueueStatus();
      setSearchQueue(nextQueue);
      setStatus((current) => (current ? { ...current, search_queue: nextQueue } : current));
    } catch (err) {
      setError(err instanceof Error ? err.message : "搜索队列读取失败");
    } finally {
      setRefreshingQueue(false);
    }
  };

  const refreshSourceHealth = async () => {
    setRefreshingSources(true);
    try {
      const nextHealth = await api.getSourceHealth(true);
      setSourceHealth(nextHealth);
      const nextHistory = await syncSourceHealthHistory();
      setStatus((current) =>
        current?.pipeline
          ? {
              ...current,
              counts: { ...current.counts, source_health_checks: nextHistory.length },
              pipeline: {
                ...current.pipeline,
                source_health: nextHealth,
              },
            }
          : current,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "源状态刷新失败");
    } finally {
      setRefreshingSources(false);
    }
  };

  const selectSupplierCsv = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 2_000_000) {
      setError("供应商 CSV 不能超过 2 MB");
      event.target.value = "";
      return;
    }
    setError("");
    setSupplierFileName(file.name);
    setSupplierCsv(await file.text());
    event.target.value = "";
  };

  const importSupplierCatalog = async () => {
    if (!supplierCsv.trim()) return;
    setSupplierBusy(true);
    setError("");
    try {
      const nextCatalog = await api.importSupplierCatalog(supplierCsv);
      setSupplierCatalog(nextCatalog);
      setSupplierCsv("");
      setSupplierFileName("");
      setConfirmingCatalogClear(false);
      await refreshSourceHealth();
      const nextStatus = await api.getSystemStatus();
      setStatus(nextStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "供应商资料导入失败");
    } finally {
      setSupplierBusy(false);
    }
  };

  const clearSupplierCatalog = async () => {
    setSupplierBusy(true);
    setError("");
    try {
      setSupplierCatalog(await api.clearSupplierCatalog());
      setConfirmingCatalogClear(false);
      await refreshSourceHealth();
      const nextStatus = await api.getSystemStatus();
      setStatus(nextStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "供应商资料清空失败");
    } finally {
      setSupplierBusy(false);
    }
  };

  const startScheduler = async () => {
    setSchedulerBusy(true);
    try {
      const nextScheduler = await api.startSourceHealthScheduler({
        interval_seconds: schedulerInterval,
        run_immediately: true,
      });
      setSourceHealthScheduler(nextScheduler);
    } catch (err) {
      setError(err instanceof Error ? err.message : "定时监控启动失败");
    } finally {
      setSchedulerBusy(false);
    }
  };

  const stopScheduler = async () => {
    setSchedulerBusy(true);
    try {
      setSourceHealthScheduler(await api.stopSourceHealthScheduler());
    } catch (err) {
      setError(err instanceof Error ? err.message : "定时监控停止失败");
    } finally {
      setSchedulerBusy(false);
    }
  };

  const runSchedulerOnce = async () => {
    setSchedulerBusy(true);
    try {
      const nextHealth = await api.runSourceHealthSchedulerOnce();
      setSourceHealth(nextHealth);
      await syncSourceHealthHistory();
      setSourceHealthScheduler(await api.getSourceHealthScheduler());
    } catch (err) {
      setError(err instanceof Error ? err.message : "定时监控运行失败");
    } finally {
      setSchedulerBusy(false);
    }
  };

  const visibleSearchQueue = searchQueue ?? status?.search_queue ?? null;

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-4xl font-semibold tracking-normal text-ink md:text-5xl">设置</h1>
        <p className="mt-3 max-w-2xl text-base leading-8 text-muted">管理分析策略、风险提示和本地开发配置。</p>
      </div>

      <div className="mb-6 grid gap-5 md:grid-cols-4">
        <MetricCard label="API 状态" value={status?.status === "ok" ? "OK" : loading ? "--" : "ERR"} detail="FastAPI 服务健康检查" icon={Server} />
        <MetricCard label="任务记录" value={status?.counts.tasks ?? 0} detail="搜索任务历史" icon={Activity} />
        <MetricCard label="报告记录" value={status?.counts.reports ?? 0} detail="可阅读与导出的报告" icon={FileArchive} />
        <MetricCard label="收藏机会" value={status?.counts.saved ?? 0} detail="已保存的机会方向" icon={ShieldCheck} />
      </div>

      {status?.account ? (
        <div className="mb-6 grid gap-4 rounded-2xl border border-line/80 bg-white p-5 shadow-panel md:grid-cols-[1fr_auto_auto_auto] md:items-center">
          <div className="flex items-center gap-4">
            <span className="grid size-11 place-items-center rounded-full bg-indigo/10 text-indigo">
              <UserRound size={19} />
            </span>
            <div>
              <p className="font-semibold text-ink">{status.account.user.username}</p>
              <p className="mt-1 text-sm text-muted">
                {status.account.user.email} · {status.account.user.plan.toUpperCase()}
              </p>
            </div>
          </div>
          <div className="rounded-xl bg-field px-4 py-3">
            <p className="text-xs text-muted">今日搜索</p>
            <p className="mt-1 font-semibold text-ink">
              {status.account.usage.searches_today} / {status.account.user.search_quota_daily}
              <span className="ml-2 text-indigo">剩余 {status.account.usage.search_remaining}</span>
            </p>
          </div>
          <div className="rounded-xl bg-field px-4 py-3">
            <p className="text-xs text-muted">本月报告</p>
            <p className="mt-1 font-semibold text-ink">
              {status.account.usage.reports_this_month} / {status.account.user.report_quota_monthly}
              <span className="ml-2 text-indigo">剩余 {status.account.usage.report_remaining}</span>
            </p>
          </div>
          <div className="rounded-xl bg-field px-4 py-3">
            <p className="text-xs text-muted">本月 AI 成本</p>
            <p className="mt-1 font-semibold text-ink">
              ${status.account.usage.ai_cost_this_month_usd.toFixed(4)}
              <span className="ml-2 text-indigo">
                {status.account.usage.ai_cost_remaining_usd == null
                  ? "不限"
                  : `剩余 $${status.account.usage.ai_cost_remaining_usd.toFixed(4)}`}
              </span>
            </p>
          </div>
        </div>
      ) : null}

      {apiLogs.length ? (
        <div className="mb-6 rounded-2xl border border-line/80 bg-white p-5 shadow-panel">
          <div className="mb-4 flex items-center gap-2">
            <Activity size={17} className="text-indigo" />
            <h2 className="font-semibold text-ink">最近账户活动</h2>
          </div>
          <div className="grid gap-2 lg:grid-cols-3">
            {apiLogs.map((log) => (
              <div key={log.id} className="rounded-xl bg-field px-3 py-3 text-xs">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-ink">{log.method} {log.endpoint}</span>
                  <span className={log.status_code < 400 ? "font-semibold text-indigo" : "font-semibold text-clay"}>{log.status_code}</span>
                </div>
                <p className="mt-2 text-muted">{log.response_time_ms} ms · {formatDateTime(log.created_at)}</p>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="系统设置">
          <div className="space-y-4">
            <label className="flex items-center justify-between gap-4 rounded-xl border border-line bg-white p-4 shadow-sm">
              <span>
                <span className="block font-medium text-ink">数据源降级</span>
                <span className="text-sm text-muted">数据源超时时保留真实已采集结果，并标记缺口。</span>
              </span>
              <input type="checkbox" defaultChecked className="size-5 accent-signal" />
            </label>
            <div className="rounded-xl border border-line bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-ink">供应商资料库</p>
                  <p className="mt-1 text-sm leading-6 text-muted">导入真实询价或供应商名录，与 Alibaba.com、EC21 公开数据共同参与供应链分析。</p>
                </div>
                <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${supplierCatalog?.count ? "bg-indigo/10 text-indigo" : "bg-field text-muted"}`}>
                  {supplierCatalog?.count ? `${supplierCatalog.count} 条` : "未导入"}
                </span>
              </div>
              <div className="mb-3 flex flex-col gap-3 rounded-lg border border-line bg-field/70 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <FileSpreadsheet size={19} className="mt-0.5 shrink-0 text-indigo" />
                  <div>
                    <p className="text-sm font-semibold text-ink">CSV 模板包含关键词、价格、MOQ、地区与链接</p>
                    <p className="mt-1 text-xs leading-5 text-muted">每次导入会替换当前账户资料库；最多 500 条、2 MB。</p>
                  </div>
                </div>
                <a
                  href={api.supplierCatalogTemplateUrl()}
                  className="focus-ring inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-ink"
                >
                  <Download size={14} />
                  下载模板
                </a>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => supplierFileInput.current?.click()}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-4 py-2 text-sm font-semibold text-ink shadow-sm transition hover:border-indigo/40"
                >
                  <Upload size={15} className="text-indigo" />
                  选择 CSV
                </button>
                <input ref={supplierFileInput} type="file" accept=".csv,text/csv" onChange={selectSupplierCsv} className="sr-only" />
                <button
                  type="button"
                  onClick={importSupplierCatalog}
                  disabled={supplierBusy || !supplierCsv.trim()}
                  className="focus-ring inline-flex items-center gap-2 rounded-lg bg-indigo px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-indigo/20 transition hover:opacity-90 disabled:opacity-60"
                >
                  {supplierBusy ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                  导入并启用
                </button>
                {confirmingCatalogClear ? (
                  <span className="inline-flex items-center gap-2 rounded-lg border border-clay/20 bg-clay/5 p-1">
                    <button
                      type="button"
                      onClick={() => setConfirmingCatalogClear(false)}
                      disabled={supplierBusy}
                      className="focus-ring rounded-md px-3 py-1.5 text-xs font-semibold text-muted disabled:opacity-60"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={clearSupplierCatalog}
                      disabled={supplierBusy}
                      className="focus-ring inline-flex items-center gap-1.5 rounded-md bg-clay px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                    >
                      <Trash2 size={13} />
                      确认清空
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmingCatalogClear(true)}
                    disabled={supplierBusy || !supplierCatalog?.count}
                    className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-4 py-2 text-sm font-semibold text-ink shadow-sm transition hover:border-clay/40 disabled:opacity-60"
                  >
                    <Trash2 size={15} />
                    清空资料库
                  </button>
                )}
                {supplierFileName ? <span className="truncate text-xs font-medium text-muted">已选择：{supplierFileName}</span> : null}
              </div>
              {supplierCatalog?.count ? (
                <div className="mt-4 rounded-lg bg-field/70 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                    <span>当前资料库：<strong className="text-ink">{supplierCatalog.count} 条供应商</strong></span>
                    {supplierCatalog.updated_at ? <span>更新于 {formatDateTime(supplierCatalog.updated_at)}</span> : null}
                  </div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {supplierCatalog.items.slice(0, 4).map((item) => (
                      <div key={item.id} className="rounded-lg border border-line bg-white px-3 py-2 text-xs">
                        <p className="truncate font-semibold text-ink">{item.supplier_name}</p>
                        <p className="mt-1 truncate text-muted">{item.keyword || "未指定关键词"} · MOQ {item.moq || "待询"}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
            <label className="flex items-center justify-between gap-4 rounded-xl border border-line bg-white p-4 shadow-sm">
              <span>
                <span className="block font-medium text-ink">专利风险提示</span>
                <span className="text-sm text-muted">报告中显示非法律意见边界声明。</span>
              </span>
              <input type="checkbox" defaultChecked className="size-5 accent-signal" />
            </label>
            <label className="flex items-center justify-between gap-4 rounded-xl border border-line bg-white p-4 shadow-sm">
              <span>
                <span className="block font-medium text-ink">本地持久化</span>
                <span className="text-sm text-muted">任务、机会、报告和收藏会写入用户本地目录。</span>
              </span>
              <input type="checkbox" defaultChecked className="size-5 accent-signal" />
            </label>
            <div className="rounded-xl border border-line bg-white p-4 shadow-sm">
              <div className="mb-3 flex items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-ink">数据源定时监控</p>
                  <p className="mt-1 text-sm text-muted">
                    当前：{sourceHealthScheduler?.running ? "运行中" : "未运行"}
                    {sourceHealthScheduler?.run_count ? ` · 已运行 ${sourceHealthScheduler.run_count} 次` : ""}
                  </p>
                </div>
                <span className={sourceHealthScheduler?.running ? "rounded-md bg-indigo/10 px-2 py-0.5 text-xs font-semibold text-indigo" : "rounded-md bg-field px-2 py-0.5 text-xs font-semibold text-muted"}>
                  {sourceHealthScheduler?.running ? "ON" : "OFF"}
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
                <select
                  value={schedulerInterval}
                  onChange={(event) => setSchedulerInterval(Number(event.target.value))}
                  className="focus-ring rounded-lg border border-line bg-field px-3 py-2 text-sm font-medium text-ink"
                  disabled={schedulerBusy || sourceHealthScheduler?.running}
                >
                  <option value={900}>每 15 分钟</option>
                  <option value={1800}>每 30 分钟</option>
                  <option value={3600}>每 1 小时</option>
                  <option value={21600}>每 6 小时</option>
                </select>
                {sourceHealthScheduler?.running ? (
                  <button type="button" onClick={stopScheduler} disabled={schedulerBusy} className="focus-ring rounded-lg border border-line bg-white px-4 py-2 text-sm font-semibold text-ink shadow-sm transition hover:border-clay/40 disabled:opacity-60">
                    停止
                  </button>
                ) : (
                  <button type="button" onClick={startScheduler} disabled={schedulerBusy} className="focus-ring rounded-lg bg-indigo px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-indigo/20 transition hover:opacity-90 disabled:opacity-60">
                    启动
                  </button>
                )}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
                {sourceHealthScheduler?.last_run_at ? <span>最近：{formatDateTime(sourceHealthScheduler.last_run_at)}</span> : null}
                {sourceHealthScheduler?.next_run_at ? <span>下次：{formatDateTime(sourceHealthScheduler.next_run_at)}</span> : null}
                {sourceHealthScheduler?.last_error ? <span className="text-clay">错误：{sourceHealthScheduler.last_error}</span> : null}
                <button type="button" onClick={runSchedulerOnce} disabled={schedulerBusy} className="font-semibold text-indigo transition hover:opacity-80 disabled:opacity-60">
                  立即运行一次
                </button>
              </div>
            </div>
          </div>
        </Section>

        <Section title="运行状态">
          {loading ? (
            <div className="flex items-center gap-2 text-muted">
              <Loader2 className="animate-spin" size={18} />
              读取系统状态...
            </div>
          ) : error ? (
            <div className="rounded-xl border border-clay/20 bg-clay/10 p-4 text-sm text-clay">{error}</div>
          ) : status ? (
            <div className="space-y-3 text-sm">
              <div className="rounded-xl border border-line bg-field/70 p-4">
                <div className="mb-2 flex items-center gap-2 font-semibold text-ink">
                  <CheckCircle2 className="text-indigo" size={17} />
                  服务在线
                </div>
                <p className="text-muted">导出格式：{status.export_formats.map((item) => item.toUpperCase()).join(" / ")}</p>
              </div>
              {status.pipeline ? (
                <div className="rounded-xl border border-line bg-field/70 p-4">
                  <p className="mb-2 font-semibold text-ink">Pipeline 模式：{status.pipeline.mode}</p>
                  <div className="flex flex-wrap gap-2">
                    {status.pipeline.enabled_sources.map((source) => (
                      <span key={source} className="rounded-lg bg-indigo/10 px-2.5 py-1 text-xs font-semibold text-indigo">
                        {source}
                      </span>
                    ))}
                  </div>
                  {status.pipeline.guarded_sources?.length ? (
                    <div className="mt-3 space-y-2">
                      {status.pipeline.guarded_sources.map((source) => (
                        <div key={source.source} className="rounded-lg border border-line bg-white px-3 py-2 text-xs leading-5 text-muted">
                          <span className="font-semibold text-ink">{source.source}</span>
                          <span className="mx-2 rounded-md bg-clay/10 px-1.5 py-0.5 font-semibold text-clay">{source.status}</span>
                          {source.reason}
                        </div>
                      ))}
                    </div>
                  ) : null}
                  <p className="mt-3 text-xs leading-5 text-muted">待接入：{status.pipeline.pending_sources.join(" / ")}</p>
                </div>
              ) : null}
              {visibleSearchQueue ? (
                <div className="rounded-xl border border-line bg-field/70 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold text-ink">搜索队列</p>
                      <p className="mt-1 text-xs text-muted">
                        {visibleSearchQueue.mode === "celery" ? "Celery / Redis" : "本地进程"} · Workers {visibleSearchQueue.worker_count} · 运行 {visibleSearchQueue.running_count} · 排队 {visibleSearchQueue.queued_count}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${queueHealthClass(visibleSearchQueue.health)}`}>
                          {queueHealthLabel(visibleSearchQueue.health)}
                        </span>
                        {visibleSearchQueue.health_reason ? (
                          <span className="text-xs text-muted">{visibleSearchQueue.health_reason}</span>
                        ) : null}
                      </div>
                      {visibleSearchQueue.broker_url ? (
                        <p className="mt-1 font-mono text-[11px] text-muted">{visibleSearchQueue.broker_url}</p>
                      ) : null}
                      {visibleSearchQueue.worker_names?.length ? (
                        <p className="mt-1 truncate font-mono text-[11px] text-muted">
                          {visibleSearchQueue.worker_names.join(" / ")}
                        </p>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      onClick={refreshSearchQueue}
                      disabled={refreshingQueue}
                      className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm transition hover:border-indigo/30 disabled:opacity-60"
                    >
                      <RefreshCw size={14} className={refreshingQueue ? "animate-spin text-indigo" : "text-indigo"} />
                      刷新
                    </button>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-4">
                    {[
                      ["活动任务", visibleSearchQueue.active_count],
                      ["运行中", visibleSearchQueue.running_count],
                      ["排队中", visibleSearchQueue.queued_count],
                      ["需重试", visibleSearchQueue.stale_non_terminal_count],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-lg bg-white px-3 py-2">
                        <p className="text-xs text-muted">{label}</p>
                        <p className="mt-1 text-lg font-semibold text-indigo">{value}</p>
                      </div>
                    ))}
                  </div>
                  {visibleSearchQueue.active_tasks.length ? (
                    <div className="mt-3 space-y-2">
                      {visibleSearchQueue.active_tasks.slice(0, 4).map((task) => (
                        <div key={task.id} className="rounded-lg border border-line bg-white px-3 py-2 text-xs">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-semibold text-ink">{task.keyword}</span>
                            <span className="rounded-md bg-indigo/10 px-2 py-0.5 font-semibold text-indigo">{task.state === "running" ? "运行中" : "排队中"}</span>
                          </div>
                          <p className="mt-1 font-mono text-muted">{task.id}</p>
                          <p className="mt-1 text-muted">
                            {task.started_at ? `开始：${formatDateTime(task.started_at)}` : task.queued_at ? `入队：${formatDateTime(task.queued_at)}` : "等待 worker 接收"}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-muted">当前没有后台搜索任务。</p>
                  )}
                </div>
              ) : null}
              {sourceHealth ? (
                <div className="rounded-xl border border-line bg-field/70 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold text-ink">数据源健康</p>
                      <p className="mt-1 text-xs text-muted">
                        OK {sourceHealth.summary.ok} · Empty {sourceHealth.summary.empty} · Guarded {sourceHealth.summary.guarded} · Error {sourceHealth.summary.error} · Not checked {sourceHealth.summary.not_checked}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={refreshSourceHealth}
                      disabled={refreshingSources}
                      className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm transition hover:border-indigo/30 disabled:opacity-60"
                    >
                      <RefreshCw size={14} className={refreshingSources ? "animate-spin text-indigo" : "text-indigo"} />
                      刷新
                    </button>
                  </div>
                  <div className="space-y-2">
                    {sourceHealth.sources.map((source) => (
                      <div key={source.key} className="rounded-lg border border-line bg-white px-3 py-2">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-medium text-ink">{source.label}</span>
                          <span className={source.available ? "rounded-md bg-indigo/10 px-2 py-0.5 text-xs font-semibold text-indigo" : "rounded-md bg-clay/10 px-2 py-0.5 text-xs font-semibold text-clay"}>
                            {source.status}
                          </span>
                        </div>
                        <p className="mt-1 text-xs leading-5 text-muted">
                          {source.reason}
                          {typeof source.latency_ms === "number" ? ` · ${source.latency_ms}ms` : ""}
                        </p>
                      </div>
                    ))}
                  </div>
                  {sourceHealthHistory.length ? (
                    <div className="mt-4 border-t border-line pt-3">
                      <p className="mb-2 text-xs font-semibold uppercase tracking-normal text-muted">Recent Checks</p>
                      <div className="space-y-2">
                        {sourceHealthHistory.map((item) => (
                          <div key={item.generated_at} className="flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2 text-xs">
                            <span className="font-medium text-ink">
                              {formatDateTime(item.generated_at)} · {item.triggered_by === "scheduler" ? "定时" : "手动"}
                            </span>
                            <span className="text-muted">
                              OK {item.summary.ok} · Empty {item.summary.empty} · Guarded {item.summary.guarded} · Error {item.summary.error}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
              <div className="rounded-xl border border-line bg-field/70 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 font-semibold text-ink">
                    <Database className="text-indigo" size={17} />
                    数据存储
                  </div>
                  <span className="rounded-md bg-indigo/10 px-2 py-0.5 text-xs font-semibold uppercase text-indigo">
                    {status.storage.backend}
                  </span>
                </div>
                <dl className="space-y-2 text-muted">
                  <div className="grid gap-1">
                    <dt className="font-semibold text-ink/80">数据库</dt>
                    <dd className="break-all font-mono text-xs">{status.storage.url}</dd>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <span>状态：{status.storage.exists ? "已连接" : "未创建"}</span>
                    {status.storage.backend === "sqlite" ? <span>大小：{formatBytes(status.storage.bytes)}</span> : null}
                  </div>
                  {status.storage.counts ? (
                    <div className="flex flex-wrap gap-2 pt-1 text-xs">
                      {Object.entries(status.storage.counts).map(([label, value]) => (
                        <span key={label} className="rounded-md bg-white px-2 py-1">
                          {label} {value}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {status.storage.migrated_from ? <p className="text-xs">已从 JSON 迁移：{status.storage.migrated_from}</p> : null}
                </dl>
                <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
                  <a href={api.dataExportUrl("zip")} className="focus-ring rounded-lg bg-indigo px-3 py-2 text-xs font-semibold text-white shadow-sm shadow-indigo/20 transition hover:opacity-90">
                    下载 ZIP 备份
                  </a>
                  <a href={api.dataExportUrl("json")} className="focus-ring rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-ink shadow-sm transition hover:border-indigo/30">
                    下载 JSON
                  </a>
                </div>
              </div>
            </div>
          ) : null}
        </Section>
      </div>
    </AppShell>
  );
}
