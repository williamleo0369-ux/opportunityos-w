export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");
export const AUTH_INVALID_EVENT = "opportunity-os:auth-invalid";
export const AUTH_OPEN_EVENT = "opportunity-os:auth-open";

export type User = {
  id: string;
  email: string;
  username: string;
  avatar_url?: string | null;
  plan: string;
  role: "user" | "admin";
  is_active: boolean;
  search_quota_daily: number;
  report_quota_monthly: number;
  ai_cost_quota_monthly?: number | null;
  created_at: string;
  updated_at: string;
};

export type UserUsage = {
  searches_today: number;
  reports_this_month: number;
  search_remaining: number;
  report_remaining: number;
  ai_cost_this_month_usd: number;
  ai_cost_remaining_usd?: number | null;
};

export type UsagePolicyPreset = {
  plan: string;
  label: string;
  search_quota_daily: number;
  report_quota_monthly: number;
  ai_cost_quota_monthly?: number | null;
};

export type AdminAgentBillingRecord = {
  id: string;
  user_id: string;
  user_email: string;
  username: string;
  task_id: string;
  opportunity_id: string;
  report_id?: string | null;
  provider?: string | null;
  model?: string | null;
  status: string;
  started_at: string;
  finished_at?: string | null;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd?: number | null;
  step_count: number;
  completed_steps: number;
  failed_steps: number;
  skipped_steps: number;
};

export type AuthResponse = {
  user: User;
  usage: UserUsage;
};

export type ApiLog = {
  id: string;
  user_id?: string | null;
  endpoint: string;
  method: string;
  status_code: number;
  request_body: {
    query?: Record<string, string>;
    body_logging?: string;
  };
  response_time_ms: number;
  created_at: string;
};

export type Opportunity = {
  id: string;
  search_task_id: string;
  product_name: string;
  product_category: string;
  short_description: string;
  opportunity_score: number;
  market_demand_score: number;
  trend_score: number;
  competition_score: number;
  patent_risk_score: number;
  innovation_score: number;
  supply_chain_score: number;
  profit_score: number;
  recommendation_level: "not_recommended" | "normal" | "recommended" | "strongly_recommended";
  estimated_price_min: number;
  estimated_price_max: number;
  estimated_market_size: string;
  main_markets: string[];
  suitable_platforms: string[];
  created_at: string;
};

export type TrendData = {
  keyword: string;
  source: string;
  country: string;
  growth_rate: number;
  trend_score: number;
  monthly_search_volume: number;
  related_keywords: string[];
  country_distribution: Record<string, number>;
  monthly_data: Array<{ month: string; value: number }>;
};

export type Patent = {
  id: string;
  patent_title: string;
  patent_number: string;
  applicant: string;
  filing_date: string;
  estimated_expiry_date: string;
  legal_status: string;
  risk_level: string;
  abstract: string;
  original_url: string;
};

export type Competitor = {
  id: string;
  product_title: string;
  platform: string;
  brand: string;
  price: number;
  currency: string;
  rating: number;
  review_count: number;
  estimated_sales: number;
  product_url: string;
  image_url: string;
  main_features: string[];
  weaknesses: string[];
};

export type PainPoint = {
  id: string;
  pain_point: string;
  frequency: number;
  sentiment: string;
  source: string;
  example_reviews: string[];
  evidence_urls: string[];
  ai_summary: string;
};

export type SupplyChainItem = {
  id: string;
  supplier_name: string;
  platform: string;
  unit_price_min: number;
  unit_price_max: number;
  moq: number;
  location: string;
  supplier_url: string;
  product_title: string;
  production_maturity_score: number;
};

export type InnovationIdea = {
  id: string;
  idea_title: string;
  idea_description: string;
  market_value_score: number;
  difficulty_score: number;
  cost_impact: string;
  differentiation_score: number;
  target_user: string;
  suggested_features: string[];
};

export type AgentStep = {
  name: string;
  label: string;
  status: string;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  request_id?: string | null;
  error?: string | null;
  output?: Record<string, unknown>;
};

export type AgentRun = {
  id: string;
  mode: string;
  provider?: string | null;
  model?: string | null;
  status: string;
  error?: string | null;
  started_at: string;
  finished_at?: string | null;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd?: number | null;
  score_reasoning?: string | null;
  risk_notice?: string | null;
  evidence_gaps?: string[];
  steps: AgentStep[];
};

export type OpportunityDetail = {
  opportunity: Opportunity;
  trend_data: TrendData[];
  patents: Patent[];
  competitors: Competitor[];
  patent_summary: Record<string, number | string>;
  competitor_summary: Record<string, number | string>;
  pain_points: PainPoint[];
  supply_chain: SupplyChainItem[];
  innovation_ideas: InnovationIdea[];
  data_quality: DataQuality;
  agent_run?: AgentRun;
  report_status: string;
  report_id: string;
};

export type DataQualitySource = {
  key: string;
  label: string;
  category: string;
  status: string;
  count: number;
  note: string;
};

export type DataQuality = {
  confidence_score: number;
  confidence_level: "high" | "medium" | "low" | string;
  category_scores: Record<string, number>;
  evidence_counts: Record<string, number>;
  sources: DataQualitySource[];
  gaps: string[];
  limitations: string[];
};

export type SearchTask = {
  id: string;
  user_id: string;
  keyword: string;
  industry?: string | null;
  target_market: string;
  language: string;
  status: string;
  progress: number;
  current_step: string;
  error_message?: string | null;
  opportunity_id?: string | null;
  report_id?: string | null;
  started_at: string;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type Report = {
  id: string;
  search_task_id: string;
  opportunity_id: string;
  user_id: string;
  report_title: string;
  executive_summary: string;
  market_analysis: string;
  trend_analysis: string;
  patent_analysis: string;
  competitor_analysis: string;
  pain_point_analysis: string;
  supply_chain_analysis: string;
  innovation_analysis: string;
  final_recommendation: string;
  data_quality_summary?: string;
  agent_run?: AgentRun;
  report_score: number;
  markdown_content: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type SystemStatus = {
  status: string;
  storage: {
    backend: "sqlite" | "postgresql" | string;
    url: string;
    path: string;
    json_path?: string;
    legacy_path: string;
    exists: boolean;
    bytes: number;
    json_exists?: boolean;
    legacy_exists: boolean;
    migrated_from?: string | null;
    counts?: Record<string, number>;
  };
  counts: {
    tasks: number;
    opportunities: number;
    reports: number;
    saved: number;
    source_health_checks?: number;
  };
  export_formats: string[];
  data_export_formats?: string[];
  account?: AuthResponse;
  source_credentials?: {
    "1688"?: SourceCredentialStatus;
  };
  search_queue?: SearchQueueStatus;
  pipeline?: {
    mode: string;
    enabled_sources: string[];
    guarded_sources?: {
      source: string;
      status: string;
      reason: string;
    }[];
    pending_sources: string[];
    source_health?: SourceHealth;
    source_health_scheduler?: SourceHealthSchedulerStatus;
  };
};

export type SearchQueueStatus = {
  mode: "local" | "celery";
  broker_url?: string | null;
  worker_count: number;
  worker_names?: string[];
  health?: "healthy" | "degraded" | "offline" | string;
  health_reason?: string | null;
  active_count: number;
  queued_count: number;
  running_count: number;
  stale_non_terminal_count: number;
  active_tasks: Array<{
    id: string;
    keyword: string;
    state: string;
    queued_at?: string | null;
    started_at?: string | null;
  }>;
};

export type SourceHealthSource = {
  key: string;
  label: string;
  category: string;
  status: string;
  available: boolean;
  reason: string;
  latency_ms?: number | null;
  checked_at: string;
  rows?: number;
  provider?: string | null;
  model?: string | null;
};

export type SourceHealth = {
  generated_at: string;
  ttl_seconds: number;
  cached: boolean;
  duration_ms: number;
  triggered_by?: string;
  summary: {
    ok: number;
    guarded: number;
    error: number;
    empty: number;
    not_checked: number;
  };
  sources: SourceHealthSource[];
};

export type SourceHealthHistory = SourceHealth[];

export type SourceHealthSchedulerStatus = {
  running: boolean;
  interval_seconds: number;
  run_count: number;
  last_started_at?: string | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_error?: string | null;
  last_summary?: SourceHealth["summary"] | null;
};

export type SourceCredentialStatus = {
  source: "account" | "environment" | "none" | string;
  configured: boolean;
  available: boolean;
  status?: string | null;
  reason?: string | null;
  url?: string | null;
  checked_at?: string | null;
};

export type AdminUserRecord = {
  user: User;
  usage: UserUsage;
  task_count: number;
  report_count: number;
  last_active_at?: string | null;
};

export type AdminLlmSettings = {
  enabled: boolean;
  configured: boolean;
  source: "database" | "environment" | "none" | string;
  provider?: string | null;
  protocol?: "openai" | "anthropic" | string | null;
  provider_label?: string | null;
  model?: string | null;
  base_url?: string | null;
  api_key_masked?: string | null;
  input_usd_per_million?: number | null;
  output_usd_per_million?: number | null;
  max_run_cost_usd?: number | null;
  updated_at?: string | null;
  available_providers?: Array<{
    value: string;
    label: string;
    protocol: "openai" | "anthropic" | string;
    default_model: string;
    default_base_url: string;
  }>;
};

export type AdminLlmTestResult = {
  ok: boolean;
  status: string;
  provider?: string;
  protocol?: string;
  provider_label?: string;
  model?: string;
  source?: string;
  latency_ms?: number;
  request_id?: string | null;
  error?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const raw = await response.text();
    let message = raw;
    try {
      const parsed = JSON.parse(raw) as { detail?: string };
      message = parsed.detail ?? raw;
    } catch {
      // Keep the upstream response text when it is not JSON.
    }
    if (
      response.status === 401 &&
      path !== "/api/auth/login" &&
      path !== "/api/auth/register" &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event(AUTH_INVALID_EVENT));
    }
    throw new Error(message || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  register(payload: { email: string; password: string; username: string }) {
    return request<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  login(payload: { email: string; password: string }) {
    return request<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  logout() {
    return request<{ status: string }>("/api/auth/logout", {
      method: "POST",
    });
  },
  me() {
    return request<AuthResponse>("/api/auth/me");
  },
  listApiLogs(limit = 20) {
    return request<ApiLog[]>(`/api/api-logs?limit=${limit}`);
  },
  createSearch(payload: { keyword: string; industry?: string; target_market: string; language: string }) {
    return request<{ task_id: string; status: string; opportunity_id?: string }>("/api/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getTask(taskId: string) {
    return request<SearchTask>(`/api/search/${taskId}`);
  },
  cancelTask(taskId: string) {
    return request<SearchTask>(`/api/search/${taskId}/cancel`, {
      method: "POST",
    });
  },
  retryTask(taskId: string) {
    return request<{ task_id: string; status: string; opportunity_id?: string | null }>(`/api/search/${taskId}/retry`, {
      method: "POST",
    });
  },
  listTasks() {
    return request<SearchTask[]>("/api/search-tasks");
  },
  listOpportunities() {
    return request<Opportunity[]>("/api/opportunities");
  },
  getOpportunity(id: string) {
    return request<OpportunityDetail>(`/api/opportunities/${id}`);
  },
  listReports() {
    return request<Report[]>("/api/reports");
  },
  getReport(id: string) {
    return request<Report>(`/api/reports/${id}`);
  },
  refreshReport(id: string) {
    return request<Report>(`/api/reports/${id}/refresh`, {
      method: "POST",
    });
  },
  generateReport(payload: { opportunity_id: string; force?: boolean }) {
    return request<{ report_id: string; status: string }>("/api/reports/generate", {
      method: "POST",
      body: JSON.stringify({ format: "markdown", ...payload }),
    });
  },
  saveOpportunity(id: string, note?: string) {
    return request<{ status: string }>(`/api/opportunities/${id}/save`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
  },
  unsaveOpportunity(id: string) {
    return request<{ status: string }>(`/api/opportunities/${id}/save`, {
      method: "DELETE",
    });
  },
  listSaved() {
    return request<Opportunity[]>("/api/saved-opportunities");
  },
  getSystemStatus() {
    return request<SystemStatus>("/api/system/status");
  },
  getSearchQueueStatus() {
    return request<SearchQueueStatus>("/api/search-queue/status");
  },
  getSourceHealth(refresh = false) {
    return request<SourceHealth>(`/api/source-health${refresh ? "?refresh=true" : ""}`);
  },
  getSourceHealthHistory(pageSize = 10) {
    return request<SourceHealthHistory>(`/api/source-health/history?page_size=${pageSize}`);
  },
  getSourceHealthScheduler() {
    return request<SourceHealthSchedulerStatus>("/api/source-health/scheduler");
  },
  startSourceHealthScheduler(payload: { interval_seconds: number; run_immediately: boolean }) {
    return request<SourceHealthSchedulerStatus>("/api/source-health/scheduler", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  stopSourceHealthScheduler() {
    return request<SourceHealthSchedulerStatus>("/api/source-health/scheduler", {
      method: "DELETE",
    });
  },
  runSourceHealthSchedulerOnce() {
    return request<SourceHealth>("/api/source-health/scheduler/run", {
      method: "POST",
    });
  },
  dataExportUrl(format: "json" | "zip") {
    return `${API_BASE_URL}/api/data/export?format=${format}`;
  },
  get1688CredentialStatus() {
    return request<SourceCredentialStatus>("/api/source-credentials/1688");
  },
  set1688Credential(cookie: string) {
    return request<SourceCredentialStatus>("/api/source-credentials/1688", {
      method: "POST",
      body: JSON.stringify({ cookie }),
    });
  },
  refresh1688Credential() {
    return request<SourceCredentialStatus>("/api/source-credentials/1688/refresh", {
      method: "POST",
    });
  },
  clear1688Credential() {
    return request<SourceCredentialStatus>("/api/source-credentials/1688", {
      method: "DELETE",
    });
  },
  listAdminUsers() {
    return request<AdminUserRecord[]>("/api/admin/users");
  },
  listAdminUsagePolicies() {
    return request<UsagePolicyPreset[]>("/api/admin/usage-policies");
  },
  listAdminAgentBilling(
    limit = 100,
    filters: { user_id?: string; status?: string } = {},
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (filters.user_id) {
      params.set("user_id", filters.user_id);
    }
    if (filters.status) {
      params.set("status", filters.status);
    }
    return request<AdminAgentBillingRecord[]>(`/api/admin/billing/agent-runs?${params.toString()}`);
  },
  adminAgentBillingCsvUrl(
    limit = 1000,
    filters: { user_id?: string; status?: string } = {},
  ) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (filters.user_id) {
      params.set("user_id", filters.user_id);
    }
    if (filters.status) {
      params.set("status", filters.status);
    }
    return `${API_BASE_URL}/api/admin/billing/agent-runs.csv?${params.toString()}`;
  },
  updateAdminUser(
    id: string,
    payload: Partial<Pick<User, "username" | "plan" | "role" | "is_active" | "search_quota_daily" | "report_quota_monthly" | "ai_cost_quota_monthly">> & {
      password?: string;
    },
  ) {
    return request<AdminUserRecord>(`/api/admin/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  },
  getAdminLlmSettings() {
    return request<AdminLlmSettings>("/api/admin/settings/llm");
  },
  saveAdminLlmSettings(payload: {
    enabled: boolean;
    provider: string;
    model: string;
    base_url: string;
    api_key?: string;
    input_usd_per_million?: number | null;
    output_usd_per_million?: number | null;
    max_run_cost_usd?: number | null;
  }) {
    return request<AdminLlmSettings>("/api/admin/settings/llm", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },
  clearAdminLlmSettings() {
    return request<AdminLlmSettings>("/api/admin/settings/llm", {
      method: "DELETE",
    });
  },
  testAdminLlmSettings() {
    return request<AdminLlmTestResult>("/api/admin/settings/llm/test", {
      method: "POST",
    });
  },
};
