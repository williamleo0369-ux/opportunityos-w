"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, FileText, Loader2, Search, Sparkles } from "lucide-react";
import { api, AUTH_OPEN_EVENT, type Report } from "@/lib/api";
import { useAuth } from "@/components/auth-provider";

const suggestedKeywords = ["pet water fountain", "camping lantern", "portable fan", "dog leash", "宠物饮水机"];

export function HomeCommandCenter() {
  const router = useRouter();
  const { user, refresh: refreshAuth } = useAuth();
  const [keyword, setKeyword] = useState("pet water fountain");
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    if (!user) {
      setReports([]);
      return;
    }
    api
      .listReports()
      .then((rows) => setReports(rows.slice(0, 3)))
      .catch(() => setReports([]));
  }, [user?.id]);

  const averageScore = useMemo(() => {
    if (reports.length === 0) return 0;
    return Math.round(reports.reduce((sum, report) => sum + report.report_score, 0) / reports.length);
  }, [reports]);

  async function waitForTask(taskId: string) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const task = await api.getTask(taskId);
      if (task.status === "completed") return task;
      if (task.status === "failed") {
        throw new Error(task.error_message || "分析任务失败");
      }
      if (task.status === "cancelled") {
        throw new Error("分析任务已取消");
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
    }
    throw new Error("分析任务超时，请前往机会探索页查看最近任务。");
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!keyword.trim()) return;
    if (!user) {
      window.dispatchEvent(new CustomEvent(AUTH_OPEN_EVENT, { detail: { mode: "login" } }));
      return;
    }

    setLoading(true);
    setError("");
    try {
      const created = await api.createSearch({
        keyword: keyword.trim(),
        industry: "Consumer Product",
        target_market: "United States",
        language: "zh-CN",
      });
      await refreshAuth();
      const task = await waitForTask(created.task_id);
      const opportunityId = task.opportunity_id ?? created.opportunity_id;
      if (!opportunityId) {
        throw new Error("任务完成但未返回机会 ID");
      }
      router.push(`/opportunities/${opportunityId}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "生成失败，请稍后重试。";
      if (message.includes("请先登录") || message.includes("会话已失效") || message.includes("账户不存在")) {
        await refreshAuth();
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-10 space-y-5">
      <form onSubmit={submit} className="rounded-2xl border border-line bg-white/80 p-2 shadow-panel backdrop-blur">
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="relative flex-1">
            <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" size={19} />
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              className="focus-ring w-full rounded-xl border border-transparent bg-field/70 py-4 pl-12 pr-4 text-base font-medium text-ink transition placeholder:text-muted/70 hover:bg-field"
              placeholder="输入行业、产品或关键词，发现下一个机会..."
            />
          </label>
          <button
            disabled={loading}
            className="focus-ring inline-flex items-center justify-center gap-3 rounded-xl bg-gradient-to-br from-indigo to-violet px-6 py-4 text-sm font-semibold text-white shadow-glow transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? <Loader2 className="animate-spin" size={18} /> : <Sparkles size={18} />}
            生成报告
          </button>
        </div>
      </form>

      <div className="flex flex-wrap gap-2">
        {suggestedKeywords.map((item) => (
          <button
            key={item}
            onClick={() => setKeyword(item)}
            className="focus-ring rounded-lg border border-line bg-white/70 px-3 py-2 text-sm font-semibold text-muted transition hover:border-indigo/30 hover:text-ink"
          >
            {item}
          </button>
        ))}
      </div>

      {error ? <p className="rounded-xl border border-clay/20 bg-clay/10 p-3 text-sm text-clay">{error}</p> : null}

      <div className="grid gap-3 md:grid-cols-[0.8fr_1.2fr]">
        <div className="rounded-2xl border border-line bg-white/75 p-5 shadow-sm">
          <p className="text-sm font-semibold text-muted">最近报告均分</p>
          <p className="electric-text mt-2 text-4xl font-semibold">{averageScore || "--"}</p>
          <p className="mt-2 text-sm leading-6 text-muted">来自本地持久化报告库</p>
        </div>

        <div className="rounded-2xl border border-line bg-white/75 p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-semibold text-muted">最近报告</p>
            <Link href="/reports" className="group inline-flex items-center gap-1 text-sm font-semibold text-indigo">
              全部
              <ArrowRight size={14} className="transition group-hover:translate-x-0.5" />
            </Link>
          </div>
          {reports.length === 0 ? (
            <p className="text-sm leading-6 text-muted">还没有报告。生成一次分析后，这里会显示最近记录。</p>
          ) : (
            <div className="space-y-2">
              {reports.map((report) => (
                <Link
                  key={report.id}
                  href={`/reports/${report.id}`}
                  className="group flex items-center justify-between gap-3 rounded-xl border border-line/80 bg-white px-3 py-3 transition hover:border-indigo/30 hover:bg-field/60"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <FileText className="shrink-0 text-indigo" size={16} />
                    <span className="truncate text-sm font-semibold text-ink">{report.report_title}</span>
                  </span>
                  <span className="electric-text shrink-0 text-sm font-semibold">{report.report_score}</span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
