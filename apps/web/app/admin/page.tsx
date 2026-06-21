"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  KeyRound,
  Loader2,
  RefreshCw,
  Save,
  ShieldCheck,
  TestTube2,
  Users,
  XCircle,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  api,
  type AdminLlmSettings,
  type AdminLlmTestResult,
  type AdminUserRecord,
} from "@/lib/api";

type LlmForm = {
  enabled: boolean;
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  input_usd_per_million: string;
  output_usd_per_million: string;
  max_run_cost_usd: string;
};

const fallbackProviders = [
  {
    value: "openai",
    label: "GPT / OpenAI",
    protocol: "openai",
    default_model: "gpt-4o-mini",
    default_base_url: "https://api.openai.com/v1",
  },
  {
    value: "deepseek",
    label: "DeepSeek",
    protocol: "openai",
    default_model: "deepseek-v4-flash",
    default_base_url: "https://api.deepseek.com",
  },
  {
    value: "gemini",
    label: "Google Gemini",
    protocol: "openai",
    default_model: "gemini-2.5-flash",
    default_base_url: "https://generativelanguage.googleapis.com/v1beta/openai",
  },
  {
    value: "anthropic",
    label: "Claude / Anthropic",
    protocol: "anthropic",
    default_model: "claude-3-5-sonnet-latest",
    default_base_url: "https://api.anthropic.com",
  },
  {
    value: "zhipu",
    label: "智谱 GLM",
    protocol: "anthropic",
    default_model: "glm-5",
    default_base_url: "https://open.bigmodel.cn/api/anthropic",
  },
  {
    value: "custom_openai",
    label: "自定义 OpenAI Compatible",
    protocol: "openai",
    default_model: "gpt-4o-mini",
    default_base_url: "https://api.openai.com/v1",
  },
  {
    value: "custom_anthropic",
    label: "自定义 Anthropic Compatible",
    protocol: "anthropic",
    default_model: "claude-3-5-sonnet-latest",
    default_base_url: "https://api.anthropic.com",
  },
] as const;

const emptyLlmForm: LlmForm = {
  enabled: true,
  provider: "deepseek",
  model: "deepseek-v4-flash",
  base_url: "https://api.deepseek.com",
  api_key: "",
  input_usd_per_million: "",
  output_usd_per_million: "",
  max_run_cost_usd: "",
};

const formatDate = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "暂无活动";

export default function AdminPage() {
  const { user, refresh: refreshAuth } = useAuth();
  const [users, setUsers] = useState<AdminUserRecord[]>([]);
  const [llm, setLlm] = useState<AdminLlmSettings | null>(null);
  const [llmForm, setLlmForm] = useState<LlmForm>(emptyLlmForm);
  const [loading, setLoading] = useState(true);
  const [savingUser, setSavingUser] = useState("");
  const [passwordDrafts, setPasswordDrafts] = useState<Record<string, string>>({});
  const [savingLlm, setSavingLlm] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);
  const [testResult, setTestResult] = useState<AdminLlmTestResult | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const providerOptions = llm?.available_providers?.length ? llm.available_providers : fallbackProviders;

  const loadAdminData = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextUsers, nextLlm] = await Promise.all([
        api.listAdminUsers(),
        api.getAdminLlmSettings(),
      ]);
      setUsers(nextUsers);
      setLlm(nextLlm);
      setLlmForm({
        enabled: nextLlm.enabled,
        provider: nextLlm.provider || "anthropic",
        model: nextLlm.model || "glm-5",
        base_url: nextLlm.base_url || "https://api.anthropic.com",
        api_key: "",
        input_usd_per_million:
          nextLlm.input_usd_per_million == null
            ? ""
            : String(nextLlm.input_usd_per_million),
        output_usd_per_million:
          nextLlm.output_usd_per_million == null
            ? ""
            : String(nextLlm.output_usd_per_million),
        max_run_cost_usd:
          nextLlm.max_run_cost_usd == null
            ? ""
            : String(nextLlm.max_run_cost_usd),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "管理数据读取失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (user?.role === "admin") {
      void loadAdminData();
    } else {
      setLoading(false);
    }
  }, [user?.id, user?.role]);

  const updateLocalUser = (
    id: string,
    patch: Partial<AdminUserRecord["user"]>,
  ) => {
    setUsers((current) =>
      current.map((item) =>
        item.user.id === id
          ? { ...item, user: { ...item.user, ...patch } }
          : item,
      ),
    );
  };

  const saveUser = async (record: AdminUserRecord) => {
    setSavingUser(record.user.id);
    setError("");
    setMessage("");
    try {
      const updated = await api.updateAdminUser(record.user.id, {
        username: record.user.username,
        plan: record.user.plan,
        role: record.user.role,
        is_active: record.user.is_active,
        search_quota_daily: Number(record.user.search_quota_daily),
        report_quota_monthly: Number(record.user.report_quota_monthly),
        ai_cost_quota_monthly:
          record.user.ai_cost_quota_monthly == null
            ? null
            : Number(record.user.ai_cost_quota_monthly),
        password: passwordDrafts[record.user.id]?.trim() || undefined,
      });
      setUsers((current) =>
        current.map((item) => (item.user.id === updated.user.id ? updated : item)),
      );
      setPasswordDrafts((current) => ({ ...current, [record.user.id]: "" }));
      if (updated.user.id === user?.id) {
        await refreshAuth();
      }
      setMessage(`${updated.user.email} 已更新`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "用户更新失败");
    } finally {
      setSavingUser("");
    }
  };

  const saveLlm = async () => {
    setSavingLlm(true);
    setError("");
    setMessage("");
    setTestResult(null);
    try {
      const next = await api.saveAdminLlmSettings({
        enabled: llmForm.enabled,
        provider: llmForm.provider,
        model: llmForm.model.trim(),
        base_url: llmForm.base_url.trim(),
        api_key: llmForm.api_key.trim() || undefined,
        input_usd_per_million: llmForm.input_usd_per_million
          ? Number(llmForm.input_usd_per_million)
          : null,
        output_usd_per_million: llmForm.output_usd_per_million
          ? Number(llmForm.output_usd_per_million)
          : null,
        max_run_cost_usd: llmForm.max_run_cost_usd
          ? Number(llmForm.max_run_cost_usd)
          : null,
      });
      setLlm(next);
      setLlmForm((current) => ({ ...current, api_key: "" }));
      setMessage("AI API 配置已加密保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI API 配置保存失败");
    } finally {
      setSavingLlm(false);
    }
  };

  const testLlm = async () => {
    setTestingLlm(true);
    setError("");
    try {
      setTestResult(await api.testAdminLlmSettings());
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI API 连接测试失败");
    } finally {
      setTestingLlm(false);
    }
  };

  if (user?.role !== "admin") {
    return (
      <AppShell>
        <div className="rounded-xl border border-line bg-white p-8 shadow-panel">
          <ShieldCheck className="text-muted" size={28} />
          <h1 className="mt-5 text-2xl font-semibold text-ink">需要管理员权限</h1>
          <p className="mt-3 text-sm text-muted">当前账户不能访问用户与 API 配置。</p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-8 flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-indigo">
            ADMIN CONTROL
          </p>
          <h1 className="mt-3 text-4xl font-semibold text-ink">管理后台</h1>
        </div>
        <button
          type="button"
          onClick={() => void loadAdminData()}
          className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-4 py-2.5 text-sm font-semibold text-ink shadow-sm hover:bg-field"
        >
          <RefreshCw size={16} />
          刷新
        </button>
      </div>

      {message ? (
        <p className="mb-5 rounded-lg border border-indigo/20 bg-indigo/10 px-4 py-3 text-sm font-semibold text-indigo">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="mb-5 rounded-lg border border-clay/20 bg-clay/10 px-4 py-3 text-sm font-semibold text-clay">
          {error}
        </p>
      ) : null}

      <section className="mb-7 border-y border-line bg-white/65 py-6">
        <div className="mb-5 flex items-center gap-3">
          <Users className="text-indigo" size={20} />
          <div>
            <h2 className="text-xl font-semibold text-ink">用户管理</h2>
            <p className="mt-1 text-sm text-muted">{users.length} 个账户</p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted">
            <Loader2 className="animate-spin" size={16} />
            正在读取用户
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1380px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th className="px-3 py-3 font-semibold">用户</th>
                  <th className="px-3 py-3 font-semibold">套餐</th>
                  <th className="px-3 py-3 font-semibold">权限</th>
                  <th className="px-3 py-3 font-semibold">重置密码</th>
                  <th className="px-3 py-3 font-semibold">每日搜索</th>
                  <th className="px-3 py-3 font-semibold">每月报告</th>
                  <th className="px-3 py-3 font-semibold">AI 月预算</th>
                  <th className="px-3 py-3 font-semibold">实际使用</th>
                  <th className="px-3 py-3 font-semibold">状态</th>
                  <th className="px-3 py-3 font-semibold">最近活动</th>
                  <th className="px-3 py-3 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {users.map((record) => (
                  <tr key={record.user.id} className="border-b border-line/70 align-top">
                    <td className="px-3 py-4">
                      <input
                        value={record.user.username}
                        onChange={(event) =>
                          updateLocalUser(record.user.id, {
                            username: event.target.value,
                          })
                        }
                        className="focus-ring w-40 rounded-md border border-line bg-white px-2.5 py-2 font-semibold text-ink"
                      />
                      <p className="mt-2 text-xs text-muted">{record.user.email}</p>
                    </td>
                    <td className="px-3 py-4">
                      <input
                        value={record.user.plan}
                        onChange={(event) =>
                          updateLocalUser(record.user.id, { plan: event.target.value })
                        }
                        className="focus-ring w-24 rounded-md border border-line bg-white px-2.5 py-2 text-ink"
                      />
                    </td>
                    <td className="px-3 py-4">
                      <select
                        value={record.user.role}
                        onChange={(event) =>
                          updateLocalUser(record.user.id, {
                            role: event.target.value as "user" | "admin",
                          })
                        }
                        className="focus-ring rounded-md border border-line bg-white px-2.5 py-2 text-ink"
                      >
                        <option value="user">用户</option>
                        <option value="admin">管理员</option>
                      </select>
                    </td>
                    <td className="px-3 py-4">
                      <input
                        type="password"
                        minLength={8}
                        value={passwordDrafts[record.user.id] ?? ""}
                        onChange={(event) =>
                          setPasswordDrafts((current) => ({
                            ...current,
                            [record.user.id]: event.target.value,
                          }))
                        }
                        placeholder="留空不修改"
                        autoComplete="new-password"
                        className="focus-ring w-32 rounded-md border border-line bg-white px-2.5 py-2 text-ink placeholder:text-muted"
                      />
                    </td>
                    <td className="px-3 py-4">
                      <input
                        type="number"
                        min={0}
                        value={record.user.search_quota_daily}
                        onChange={(event) =>
                          updateLocalUser(record.user.id, {
                            search_quota_daily: Number(event.target.value),
                          })
                        }
                        className="focus-ring w-24 rounded-md border border-line bg-white px-2.5 py-2 text-ink"
                      />
                    </td>
                    <td className="px-3 py-4">
                      <input
                        type="number"
                        min={0}
                        value={record.user.report_quota_monthly}
                        onChange={(event) =>
                          updateLocalUser(record.user.id, {
                            report_quota_monthly: Number(event.target.value),
                          })
                        }
                        className="focus-ring w-24 rounded-md border border-line bg-white px-2.5 py-2 text-ink"
                      />
                    </td>
                    <td className="px-3 py-4">
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        value={record.user.ai_cost_quota_monthly ?? ""}
                        onChange={(event) =>
                          updateLocalUser(record.user.id, {
                            ai_cost_quota_monthly: event.target.value
                              ? Number(event.target.value)
                              : null,
                          })
                        }
                        placeholder="不限"
                        className="focus-ring w-24 rounded-md border border-line bg-white px-2.5 py-2 text-ink placeholder:text-muted"
                      />
                    </td>
                    <td className="px-3 py-4 text-muted">
                      <p>今日 {record.usage.searches_today}</p>
                      <p className="mt-1">本月 {record.usage.reports_this_month}</p>
                      <p className="mt-1">
                        AI ${record.usage.ai_cost_this_month_usd.toFixed(4)}
                        {record.usage.ai_cost_remaining_usd == null
                          ? " · 不限"
                          : ` · 剩余 $${record.usage.ai_cost_remaining_usd.toFixed(4)}`}
                      </p>
                      <p className="mt-1 text-xs">
                        {record.task_count} 任务 · {record.report_count} 报告
                      </p>
                    </td>
                    <td className="px-3 py-4">
                      <label className="inline-flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={record.user.is_active}
                          onChange={(event) =>
                            updateLocalUser(record.user.id, {
                              is_active: event.target.checked,
                            })
                          }
                          className="size-4 accent-[#5B5CF6]"
                        />
                        <span
                          className={
                            record.user.is_active ? "text-indigo" : "text-clay"
                          }
                        >
                          {record.user.is_active ? "启用" : "停用"}
                        </span>
                      </label>
                    </td>
                    <td className="px-3 py-4 text-xs text-muted">
                      {formatDate(record.last_active_at)}
                    </td>
                    <td className="px-3 py-4">
                      <button
                        type="button"
                        onClick={() => void saveUser(record)}
                        disabled={savingUser === record.user.id}
                        className="focus-ring inline-flex items-center gap-2 rounded-md bg-indigo px-3 py-2 font-semibold text-white disabled:opacity-50"
                      >
                        {savingUser === record.user.id ? (
                          <Loader2 className="animate-spin" size={14} />
                        ) : (
                          <Save size={14} />
                        )}
                        保存
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="border-y border-line bg-white/65 py-6">
        <div className="mb-6 flex flex-col justify-between gap-3 md:flex-row md:items-center">
          <div className="flex items-center gap-3">
            <KeyRound className="text-indigo" size={20} />
            <div>
              <h2 className="text-xl font-semibold text-ink">AI API 配置</h2>
              <p className="mt-1 text-sm text-muted">
                {llm?.configured
                  ? `${llm.provider_label || llm.provider} / ${llm.model} · ${llm.source}`
                  : "尚未配置"}
              </p>
            </div>
          </div>
          {llm?.api_key_masked ? (
            <span className="rounded-md bg-field px-3 py-2 font-mono text-xs text-muted">
              {llm.api_key_masked}
            </span>
          ) : null}
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <label className="block">
            <span className="text-sm font-semibold text-ink">Provider</span>
            <select
              value={llmForm.provider}
              onChange={(event) => {
                const nextProvider = providerOptions.find((item) => item.value === event.target.value);
                setLlmForm((current) => ({
                  ...current,
                  provider: event.target.value,
                  model: nextProvider?.default_model ?? current.model,
                  base_url: nextProvider?.default_base_url ?? current.base_url,
                }));
              }}
              className="focus-ring mt-2 w-full rounded-lg border border-line bg-white px-3 py-3 text-ink"
            >
              {providerOptions.map((provider) => (
                <option key={provider.value} value={provider.value}>
                  {provider.label} ({provider.protocol})
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-ink">模型</span>
            <input
              value={llmForm.model}
              onChange={(event) =>
                setLlmForm((current) => ({ ...current, model: event.target.value }))
              }
              className="focus-ring mt-2 w-full rounded-lg border border-line bg-white px-3 py-3 text-ink"
            />
          </label>
          <label className="block md:col-span-2">
            <span className="text-sm font-semibold text-ink">Base URL</span>
            <input
              value={llmForm.base_url}
              onChange={(event) =>
                setLlmForm((current) => ({
                  ...current,
                  base_url: event.target.value,
                }))
              }
              className="focus-ring mt-2 w-full rounded-lg border border-line bg-white px-3 py-3 font-mono text-sm text-ink"
            />
          </label>
          <label className="block md:col-span-2">
            <span className="text-sm font-semibold text-ink">API Key</span>
            <input
              type="password"
              value={llmForm.api_key}
              onChange={(event) =>
                setLlmForm((current) => ({
                  ...current,
                  api_key: event.target.value,
                }))
              }
              placeholder={
                llm?.configured ? "留空则保留已加密的现有 Key" : "输入真实 API Key"
              }
              autoComplete="new-password"
              className="focus-ring mt-2 w-full rounded-lg border border-line bg-white px-3 py-3 font-mono text-sm text-ink placeholder:text-muted"
            />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-ink">
              输入价格 USD / 1M Token
            </span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={llmForm.input_usd_per_million}
              onChange={(event) =>
                setLlmForm((current) => ({
                  ...current,
                  input_usd_per_million: event.target.value,
                }))
              }
              className="focus-ring mt-2 w-full rounded-lg border border-line bg-white px-3 py-3 text-ink"
            />
          </label>
          <label className="block">
            <span className="text-sm font-semibold text-ink">
              输出价格 USD / 1M Token
            </span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={llmForm.output_usd_per_million}
              onChange={(event) =>
                setLlmForm((current) => ({
                  ...current,
                  output_usd_per_million: event.target.value,
                }))
              }
              className="focus-ring mt-2 w-full rounded-lg border border-line bg-white px-3 py-3 text-ink"
            />
          </label>
          <label className="block md:col-span-2">
            <span className="text-sm font-semibold text-ink">
              单次 Agent 预算 USD
            </span>
            <input
              type="number"
              min={0}
              step="0.001"
              value={llmForm.max_run_cost_usd}
              onChange={(event) =>
                setLlmForm((current) => ({
                  ...current,
                  max_run_cost_usd: event.target.value,
                }))
              }
              placeholder="留空不限制；超预算时自动使用规则降级"
              className="focus-ring mt-2 w-full rounded-lg border border-line bg-white px-3 py-3 text-ink placeholder:text-muted"
            />
            <p className="mt-2 text-xs leading-5 text-muted">
              需要同时填写输入/输出单价。预算不足时会跳过后续 AI 阶段，报告仍基于真实证据生成。
            </p>
          </label>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
            <input
              type="checkbox"
              checked={llmForm.enabled}
              onChange={(event) =>
                setLlmForm((current) => ({
                  ...current,
                  enabled: event.target.checked,
                }))
              }
              className="size-4 accent-[#5B5CF6]"
            />
            启用真实 AI Agent
          </label>
          <button
            type="button"
            onClick={() => void saveLlm()}
            disabled={savingLlm}
            className="focus-ring inline-flex items-center gap-2 rounded-lg bg-indigo px-4 py-2.5 text-sm font-semibold text-white shadow-sm disabled:opacity-50"
          >
            {savingLlm ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <Save size={16} />
            )}
            保存配置
          </button>
          <button
            type="button"
            onClick={() => void testLlm()}
            disabled={testingLlm || !llm?.configured}
            className="focus-ring inline-flex items-center gap-2 rounded-lg border border-line bg-white px-4 py-2.5 text-sm font-semibold text-ink shadow-sm disabled:opacity-50"
          >
            {testingLlm ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <TestTube2 size={16} />
            )}
            测试连接
          </button>
        </div>

        {testResult ? (
          <div
            className={`mt-5 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${
              testResult.ok
                ? "border-indigo/20 bg-indigo/10 text-indigo"
                : "border-clay/20 bg-clay/10 text-clay"
            }`}
          >
            {testResult.ok ? (
              <CheckCircle2 className="mt-0.5 shrink-0" size={17} />
            ) : (
              <XCircle className="mt-0.5 shrink-0" size={17} />
            )}
            <div>
              <p className="font-semibold">
                {testResult.ok ? "连接成功" : "连接失败"}
              </p>
              <p className="mt-1 break-all">
                {testResult.ok
                  ? `${testResult.provider}/${testResult.model} · ${testResult.latency_ms}ms`
                  : testResult.error}
              </p>
            </div>
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}
