# OpportunityOS

OpportunityOS is an AI product opportunity discovery MVP. It follows the supplied V1.0 technical design and ships a runnable local loop:

1. Enter a product keyword.
2. Register or sign in to an isolated workspace.
3. Create a search task within the account quota.
4. Run the analysis task in the API background worker while the frontend polls task progress.
5. View a private product opportunity detail page and report center.

## Stack

- Frontend: Next.js, TypeScript, Tailwind CSS, lucide-react, Recharts
- Backend: FastAPI, Pydantic
- Database: SQLite by default, PostgreSQL 16 for shared/deployed environments
- Queue: Redis and Celery, with an in-process local fallback

The current MVP stores entities in a transactional database and uses real-source collectors for the P0 loop. SQLite works without extra services; PostgreSQL is enabled through `OPPORTUNITY_OS_DATABASE_URL`. Search tasks can run on Redis/Celery workers and commit progress plus final evidence atomically, so API restarts do not interrupt active worker jobs. LLM agent orchestration is enabled when compatible provider credentials are configured; otherwise the product keeps rule-based output from the same real-source data.
Accounts use salted `scrypt` password hashes and signed HttpOnly sessions. Tasks, opportunities, reports, downloads, exports, and saved items are authorization-checked by owner. Starter accounts default to 20 searches per day and 100 reports per month, configurable through environment variables.
When the LLM layer is unavailable, innovation ideas are generated only from collected evidence such as pain points, patents, competitor listings, and supplier rows; generic simulated opportunity ideas are not emitted.
Search analysis runs asynchronously, so `POST /api/search` returns a task immediately and clients poll `GET /api/search/{task_id}` until completion. Local mode uses an in-process pool; Celery mode uses Redis and separate worker processes.
Running search tasks can be cancelled, and failed/cancelled tasks can be retried from their original request payload.
Opportunity detail responses include a computed data-quality summary so users can see which real sources were collected, which sources were empty or guarded, and which evidence gaps should be resolved before higher-cost decisions.
Pain-point records retain direct evidence URLs when available. New searches expose Amazon review anchors, Reddit discussion links, Google Patents pages, or marketplace listing URLs alongside the extracted text snippets.

Current real sources:

- Google Suggest and Amazon Suggest for keyword expansion and demand signals
- Wikimedia Search/Pageviews for public trend signal enrichment
- Google Patents XHR for patent intelligence
- Amazon Search HTML for marketplace listing, price, rating, and product URL extraction
- Amazon Product Page Reviews for review-snippet pain-point extraction when product pages expose reviews
- Reddit Search RSS for public discussion and pain-point extraction
- Alibaba.com Search HTML for supplier listing, MOQ, pricing, review score, and product URL extraction
- 1688 Search HTML for supplier rows only when `OPPORTUNITY_OS_1688_COOKIE` is configured with a valid session
- EC21 B2B Market for supplier listing, MOQ, pricing, origin, and contact URL extraction
- LLM Agent orchestration through GPT/OpenAI, DeepSeek, Claude/Anthropic-compatible, Zhipu GLM, or custom compatible chat APIs when credentials are configured

Still pending:

- Valid 1688 session cookie provisioning/refresh; without it, public search returns anti-bot verification in this runtime

## Quick Start

```bash
cd /Users/williamleo/Documents/opportunity-os
npm install
npm run install:api
npm run dev:api
```

In a second terminal:

```bash
cd /Users/williamleo/Documents/opportunity-os
npm run dev:web
```

Open `http://localhost:3000`.

By default, persisted data is stored in SQLite at `~/.opportunity-os/opportunity-os.db`. On first startup, an existing `~/.opportunity-os/store.json` is imported automatically and retained as a backup.

To use PostgreSQL:

```bash
docker compose up -d postgres
export OPPORTUNITY_OS_DATABASE_URL="postgresql://opportunity:opportunity@127.0.0.1:5432/opportunity_os"
npm run dev:api
```

`OPPORTUNITY_OS_DATABASE_URL` accepts `sqlite:///...` or `postgresql://...`. PostgreSQL passwords are removed from `/api/system/status` output.

To run the production-style PostgreSQL + Redis/Celery path locally:

```bash
docker compose up -d postgres redis
export OPPORTUNITY_OS_DATABASE_URL="postgresql://opportunity:opportunity@127.0.0.1:5432/opportunity_os"
export REDIS_URL="redis://127.0.0.1:6379/0"
export OPPORTUNITY_OS_TASK_QUEUE="celery"
npm run dev:worker
```

Start `npm run dev:api` in another terminal with the same environment. Celery tasks persist progress and final results directly to the shared database. The API refreshes distributed state from that database, and cancellation remains cooperative between source-collection stages.

The web app uses a same-origin `/api` proxy by default. `OPPORTUNITY_OS_API_ORIGIN`
selects the server-side API target and defaults to `http://127.0.0.1:8000`. This
avoids session-cookie failures caused by mixing `localhost` and `127.0.0.1`.
Only set `NEXT_PUBLIC_API_BASE_URL` for a deliberately separate HTTPS API origin
whose CORS and cross-site cookie settings are configured.

To expose the current local stack through a temporary public HTTPS URL:

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:3000 --no-autoupdate
```

The generated `https://*.trycloudflare.com` URL points at the same Next.js app,
which proxies `/api` to the local FastAPI server. Keep the API, web server,
worker, PostgreSQL/Redis, and `cloudflared` process running while using that
link. For a permanent production URL, deploy the web/API services and a worker
against hosted PostgreSQL and Redis, or configure a named Cloudflare Tunnel.

Optional real-source credentials:

- `OPPORTUNITY_OS_DATABASE_URL`: optional database connection URL. Defaults to local SQLite; use the Docker Compose PostgreSQL URL above for a shared database.
- `OPPORTUNITY_OS_1688_COOKIE`: authenticated 1688 browser cookie string. If unset or expired, 1688 is reported as guarded/missing-session and no synthetic 1688 supplier rows are generated.
- `OPENAI_API_KEY` plus optional `OPENAI_MODEL`/`OPENAI_BASE_URL`, `DEEPSEEK_API_KEY` plus optional `DEEPSEEK_MODEL`/`DEEPSEEK_BASE_URL`, `ZHIPU_API_KEY` plus optional `ZHIPU_MODEL`/`ZHIPU_BASE_URL`, or `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` plus optional `ANTHROPIC_MODEL`/`ANTHROPIC_BASE_URL`: enables the LLM agent. Admins can also configure the provider, model, Base URL, and API key from `/admin`; saved keys are encrypted. The default DeepSeek model is `deepseek-v4-flash` with Base URL `https://api.deepseek.com`.
- `OPPORTUNITY_OS_LLM_PROVIDER`: optional `auto`, `openai`, `deepseek`, `anthropic`, or `zhipu`; defaults to `auto`.
- `OPPORTUNITY_OS_LLM_TIMEOUT_SECONDS`: optional LLM request timeout, defaults to `25`; timed-out agent calls fall back to evidence-based rule output.
- `OPPORTUNITY_OS_AGENT_PARALLELISM`: specialist Agent concurrency from `1` to `3`; defaults to `1` to respect rate-limited model gateways.
- `OPPORTUNITY_OS_LLM_INPUT_USD_PER_MILLION` / `OPPORTUNITY_OS_LLM_OUTPUT_USD_PER_MILLION`: optional model rates used to estimate Agent Run cost. Without them, token usage is recorded but dollar cost remains unset.
- `OPPORTUNITY_OS_SOURCE_HEALTH_INTERVAL_SECONDS`: optional interval, minimum 60 seconds. When set, the API process starts scheduled source-health checks on boot and persists snapshots to the local store.
- `OPPORTUNITY_OS_TASK_QUEUE`: `local` by default, or `celery` for the Redis-backed distributed queue.
- `REDIS_URL`: Celery broker and result-backend URL; defaults to `redis://127.0.0.1:6379/0`. Railway-style `REDIS_PRIVATE_URL`, `REDIS_PUBLIC_URL`, and `RAILWAY_REDIS_URL` are also recognized.
- `OPPORTUNITY_OS_SEARCH_WORKERS`: local worker count and recommended Celery concurrency; defaults to `2`.
- `OPPORTUNITY_OS_DEFAULT_SEARCH_QUOTA_DAILY`: search allowance assigned to new accounts; defaults to `20`.
- `OPPORTUNITY_OS_DEFAULT_REPORT_QUOTA_MONTHLY`: report allowance assigned to new accounts; defaults to `100`.
- `OPPORTUNITY_OS_ADMIN_EMAILS`: comma-separated emails that receive the `admin` role when they register. Admins can manage users and AI API settings from `/admin`.
- `OPPORTUNITY_OS_SESSION_TTL_DAYS`: signed session lifetime; defaults to `30`.
- `OPPORTUNITY_OS_AUTH_SECRET`: production signing secret. Local development creates a persistent secret at `~/.opportunity-os/auth-secret`.
- `OPPORTUNITY_OS_SECURE_COOKIES`: set to `true` behind HTTPS.
- `OPPORTUNITY_OS_COOKIE_SAMESITE`: defaults to `lax`; use `none` together with secure cookies when frontend and API are on different HTTPS sites.
- `OPPORTUNITY_OS_CORS_ORIGINS`: comma-separated allowed frontend origins; defaults to local ports.

1688 can also be connected from the Settings page. The cookie is encrypted with server-side key material, stored per account, read directly by Celery workers, and excluded from API responses, logs, and JSON/ZIP exports. An account credential overrides `OPPORTUNITY_OS_1688_COOKIE` for that user's searches.

In local mode, an API restart marks interrupted jobs failed with a retryable message. In Celery mode, queued and running tasks are not failed by an API restart because workers continue independently and write their results to the shared database.
New reports include a "Data Sources and Confidence" section in Markdown, PDF, Excel, and Word exports.
Configured LLM runs use five traceable stages: trend/market, patent risk, commercial evidence, innovation, and scoring/report. Every report stores stage status, latency, token usage, request IDs, bounded structured outputs, and failure reasons; API keys and full prompts are never persisted.
Existing reports can be refreshed from the stored real evidence without rerunning crawlers; the report id is preserved and the data-quality section is added when missing.

## Implemented API

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/admin/users`
- `PATCH /api/admin/users/{user_id}`
- `GET /api/admin/settings/llm`
- `PUT /api/admin/settings/llm`
- `DELETE /api/admin/settings/llm`
- `POST /api/admin/settings/llm/test`
- `GET /api/api-logs?limit=20`
- `POST /api/search`
- `GET /api/search/{task_id}`
- `POST /api/search/{task_id}/cancel`
- `POST /api/search/{task_id}/retry`
- `GET /api/search-queue/status`
- `GET /api/search-tasks`
- `GET /api/system/status`
- `GET /api/source-health?refresh=true`
- `GET /api/source-health/history?page_size=10`
- `GET /api/source-health/scheduler`
- `POST /api/source-health/scheduler`
- `DELETE /api/source-health/scheduler`
- `POST /api/source-health/scheduler/run`
- `GET /api/source-credentials/1688`
- `POST /api/source-credentials/1688`
- `DELETE /api/source-credentials/1688`
- `GET /api/data/export?format=zip`
- `GET /api/data/export?format=json`
- `GET /api/opportunities`
- `GET /api/opportunities/{id}`
- `GET /api/opportunities/{id}/trends`
- `GET /api/opportunities/{id}/patents`
- `GET /api/opportunities/{id}/competitors`
- `GET /api/opportunities/{id}/pain-points`
- `GET /api/opportunities/{id}/supply-chain`
- `GET /api/opportunities/{id}/innovation-ideas`
- `POST /api/reports/generate`
- `GET /api/reports`
- `GET /api/reports/{id}`
- `POST /api/reports/{id}/refresh`
- `GET /api/reports/{id}/download?format=markdown`
- `POST /api/opportunities/{id}/save`
- `DELETE /api/opportunities/{id}/save`
- `GET /api/saved-opportunities`

## Next Development Steps

- Add Gemini/local model provider adapters after OpenAI/Anthropic routing.
- Replace full-state refreshes with endpoint-specific repository queries as data volume grows.
- Add production worker monitoring, retry/backoff policies, and scheduled source health checks.
