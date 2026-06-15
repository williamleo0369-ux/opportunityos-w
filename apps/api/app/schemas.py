from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


TaskStatus = Literal[
    "pending",
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
    "failed",
    "cancelled",
]

RecommendationLevel = Literal[
    "not_recommended",
    "normal",
    "recommended",
    "strongly_recommended",
]


class User(BaseModel):
    id: str
    email: str
    username: str
    avatar_url: str | None = None
    plan: str
    role: Literal["user", "admin"] = "user"
    is_active: bool = True
    search_quota_daily: int
    report_quota_monthly: int
    created_at: datetime
    updated_at: datetime


class UserUsage(BaseModel):
    searches_today: int
    reports_this_month: int
    search_remaining: int
    report_remaining: int


class AuthResponse(BaseModel):
    user: User
    usage: UserUsage


class ApiLog(BaseModel):
    id: str
    user_id: str | None = None
    endpoint: str
    method: str
    status_code: int
    request_body: dict[str, Any]
    response_time_ms: int
    created_at: datetime


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    username: str = Field(min_length=2, max_length=50)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class SearchRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=120)
    industry: str | None = None
    target_market: str = "United States"
    language: str = "zh-CN"


class SearchTask(BaseModel):
    id: str
    user_id: str
    keyword: str
    industry: str | None
    target_market: str
    language: str
    status: TaskStatus
    progress: int
    current_step: TaskStatus
    error_message: str | None = None
    opportunity_id: str | None = None
    report_id: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SearchResponse(BaseModel):
    task_id: str
    status: TaskStatus
    opportunity_id: str | None = None


class TrendData(BaseModel):
    id: str
    opportunity_id: str
    keyword: str
    source: str
    country: str
    time_period: str
    growth_rate: float
    trend_score: int
    monthly_search_volume: int
    related_keywords: list[str]
    country_distribution: dict[str, int]
    monthly_data: list[dict[str, Any]]
    raw_data: dict[str, Any]
    created_at: datetime


class Patent(BaseModel):
    id: str
    opportunity_id: str
    patent_title: str
    patent_number: str
    country: str
    applicant: str
    inventor: str
    filing_date: str
    publication_date: str
    grant_date: str | None
    estimated_expiry_date: str
    legal_status: str
    risk_level: str
    abstract: str
    claims: list[str]
    original_url: str
    raw_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class Competitor(BaseModel):
    id: str
    opportunity_id: str
    product_title: str
    platform: str
    brand: str
    price: float
    currency: str
    rating: float
    review_count: int
    estimated_sales: int
    product_url: str
    image_url: str
    main_features: list[str]
    weaknesses: list[str]
    raw_data: dict[str, Any]
    created_at: datetime


class PainPoint(BaseModel):
    id: str
    opportunity_id: str
    pain_point: str
    frequency: int
    sentiment: str
    source: str
    example_reviews: list[str]
    evidence_urls: list[str] = Field(default_factory=list)
    ai_summary: str
    created_at: datetime


class SupplyChainItem(BaseModel):
    id: str
    opportunity_id: str
    supplier_name: str
    platform: str
    product_title: str
    unit_price_min: float
    unit_price_max: float
    moq: int
    location: str
    supplier_url: str
    production_maturity_score: int
    logistics_note: str
    raw_data: dict[str, Any]
    created_at: datetime


class InnovationIdea(BaseModel):
    id: str
    opportunity_id: str
    idea_title: str
    idea_description: str
    market_value_score: int
    difficulty_score: int
    cost_impact: str
    differentiation_score: int
    target_user: str
    suggested_features: list[str]
    created_at: datetime


class Opportunity(BaseModel):
    id: str
    search_task_id: str
    user_id: str
    product_name: str
    product_category: str
    short_description: str
    opportunity_score: int
    market_demand_score: int
    trend_score: int
    competition_score: int
    patent_risk_score: int
    innovation_score: int
    supply_chain_score: int
    profit_score: int
    recommendation_level: RecommendationLevel
    estimated_price_min: float
    estimated_price_max: float
    estimated_market_size: str
    main_markets: list[str]
    suitable_platforms: list[str]
    created_at: datetime
    updated_at: datetime


class Report(BaseModel):
    id: str
    search_task_id: str
    opportunity_id: str
    user_id: str
    report_title: str
    executive_summary: str
    market_analysis: str
    trend_analysis: str
    patent_analysis: str
    competitor_analysis: str
    pain_point_analysis: str
    supply_chain_analysis: str
    innovation_analysis: str
    final_recommendation: str
    data_quality_summary: str = ""
    agent_run: dict[str, Any] = Field(default_factory=dict)
    report_score: int
    pdf_url: str | None = None
    excel_url: str | None = None
    markdown_content: str
    status: str
    created_at: datetime
    updated_at: datetime


class OpportunityDetail(BaseModel):
    opportunity: Opportunity
    trend_data: list[TrendData]
    patents: list[Patent]
    competitors: list[Competitor]
    patent_summary: dict[str, Any]
    competitor_summary: dict[str, Any]
    pain_points: list[PainPoint]
    supply_chain: list[SupplyChainItem]
    innovation_ideas: list[InnovationIdea]
    data_quality: dict[str, Any]
    agent_run: dict[str, Any] = Field(default_factory=dict)
    report_status: str
    report_id: str


class ReportRequest(BaseModel):
    opportunity_id: str
    format: Literal["markdown", "pdf", "excel", "word"] = "markdown"
    force: bool = False


class SaveRequest(BaseModel):
    note: str | None = None


class SourceHealthSchedulerRequest(BaseModel):
    interval_seconds: int = Field(default=3600, ge=60, le=86400)
    run_immediately: bool = True


class SourceCredentialRequest(BaseModel):
    cookie: str = Field(min_length=8, max_length=60000)


class AdminUserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=80)
    plan: str | None = Field(default=None, min_length=2, max_length=40)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None
    search_quota_daily: int | None = Field(default=None, ge=0, le=100000)
    report_quota_monthly: int | None = Field(default=None, ge=0, le=100000)


class AdminUserRecord(BaseModel):
    user: User
    usage: UserUsage
    task_count: int
    report_count: int
    last_active_at: datetime | None = None


class AdminLlmSettingsRequest(BaseModel):
    enabled: bool = True
    provider: str = Field(min_length=2, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, min_length=8, max_length=10000)
    input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float | None = Field(default=None, ge=0)
