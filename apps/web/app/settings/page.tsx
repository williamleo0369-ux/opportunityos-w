"use client";

import { useEffect, useState } from "react";
import { Activity, CheckCircle2, Database, FileArchive, Loader2, RefreshCw, Server, ShieldCheck, UserRound } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { MetricCard, Section } from "@/components/ui";
import { api, type ApiLog, type SearchQueueStatus, type SourceCredentialStatus, type SourceHealth, type SourceHealthHistory, type SourceHealthSchedulerStatus, type SystemStatus } from "@/lib/api";

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

export default function SettingsPage() {
  const { user } = useAuth();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [sourceHealth, setSourceHealth] = useState<SourceHealth | null>(null);
  const [sourceHealthHistory, setSourceHealthHistory] = useState<SourceHealthHistory>([]);
  const [sourceHealthScheduler, setSourceHealthScheduler] = useState<SourceHealthSchedulerStatus | null>(null);
  const [searchQueue, setSearchQueue] = useState<SearchQueueStatus | null>(null);
  const [credential1688, setCredential1688] = useState<SourceCredentialStatus | null>(null);
  const [apiLogs, setApiLogs] = useState<ApiLog[]>([]);
  const [cookie1688, setCookie1688] = useState("");
  const [schedulerInterval, setSchedulerInterval] = useState(3600);
  const [loading, setLoading] = useState(true);
  const [refreshingSources, setRefreshingSources] = useState(false);
  const [refreshingQueue, setRefreshingQueue] = useState(false);
  const [schedulerBusy, setSchedulerBusy] = useState(false);
  const [credentialBusy, setCredentialBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    setError("");
    Promise.all([api.getSystemStatus(), api.getSourceHealthHistory(5), api.getSourceHealthScheduler(), api.getSearchQueueStatus(), api.listApiLogs(6)])
      .then(([nextStatus, nextHistory, nextScheduler, nextQueue, nextLogs]) => {
        setStatus(nextStatus);
        setSourceHealth(nextStatus.pipeline?.source_health ?? null);
        setSourceHealthHistory(nextHistory);
        setSourceHealthScheduler(nextScheduler);
        setSearchQueue(nextQueue);
        setCredential1688(nextStatus.source_credentials?.["1688"] ?? null);
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

  const connect1688 = async () => {
    const cookie = cookie1688.trim();
    if (!cookie) return;
    setCredentialBusy(true);
    try {
      const nextCredential = await api.set1688Credential(cookie);
      setCredential1688(nextCredential);
      setCookie1688("");
      await refreshSourceHealth();
      const nextStatus = await api.getSystemStatus();
      setStatus(nextStatus);
      setCredential1688(nextStatus.source_credentials?.["1688"] ?? nextCredential);
    } catch (err) {
      setError(err instanceof Error ? err.message : "1688 会话检测失败");
    } finally {
      setCredentialBusy(false);
    }
  };

  const clear1688 = async () => {
    setCredentialBusy(true);
    try {
      const nextCredential = await api.clear1688Credential();
      setCredential1688(nextCredential);
      await refreshSourceHealth();
      const nextStatus = await api.getSystemStatus();
      setStatus(nextStatus);
      setCredential1688(nextStatus.source_credentials?.["1688"] ?? nextCredential);
    } catch (err) {
      setError(err instanceof Error ? err.message : "1688 会话清除失败");
    } finally {
      setCredentialBusy(false);
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
        <div className="mb-6 grid gap-4 rounded-2xl border border-line/80 bg-white p-5 shadow-panel md:grid-cols-[1fr_auto_auto] md:items-center">
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
                  <p className="font-medium text-ink">1688 会话 Cookie</p>
                  <p className="mt-1 text-sm text-muted">加密保存到当前账户，后台 worker 将在真实供应链采集中使用。</p>
                </div>
                <span className={credential1688?.available ? "rounded-md bg-indigo/10 px-2 py-0.5 text-xs font-semibold text-indigo" : "rounded-md bg-clay/10 px-2 py-0.5 text-xs font-semibold text-clay"}>
                  {credential1688?.source === "account" ? "ACCOUNT" : credential1688?.source === "environment" ? "ENV" : "OFF"}
                </span>
              </div>
              <textarea
                value={cookie1688}
                onChange={(event) => setCookie1688(event.target.value)}
                placeholder="粘贴从浏览器复制的 1688 Cookie"
                spellCheck={false}
                className="focus-ring min-h-24 w-full resize-y rounded-lg border border-line bg-field px-3 py-2 font-mono text-xs text-ink placeholder:text-muted/70"
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={connect1688}
                  disabled={credentialBusy || cookie1688.trim().length < 8}
                  className="focus-ring rounded-lg bg-indigo px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-indigo/20 transition hover:opacity-90 disabled:opacity-60"
                >
                  保存并检测
                </button>
                <button
                  type="button"
                  onClick={clear1688}
                  disabled={credentialBusy || !credential1688?.configured}
                  className="focus-ring rounded-lg border border-line bg-white px-4 py-2 text-sm font-semibold text-ink shadow-sm transition hover:border-clay/40 disabled:opacity-60"
                >
                  清除会话
                </button>
              </div>
              {credential1688 ? (
                <p className="mt-3 text-xs leading-5 text-muted">
                  状态：<span className="font-semibold text-ink">{credential1688.status ?? "unknown"}</span>
                  {credential1688.reason ? ` · ${credential1688.reason}` : ""}
                  {credential1688.checked_at ? ` · 检测于 ${formatDateTime(credential1688.checked_at)}` : ""}
                </p>
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
                      {visibleSearchQueue.broker_url ? (
                        <p className="mt-1 font-mono text-[11px] text-muted">{visibleSearchQueue.broker_url}</p>
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
