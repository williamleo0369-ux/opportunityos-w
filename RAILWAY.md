# Railway Deployment

This repository is ready to deploy from GitHub to Railway as three services plus managed PostgreSQL and Redis.

## Services

Create these services from the same GitHub repository:

1. `opportunityos-web`
   - Dockerfile path: `apps/web/Dockerfile`
   - Public domain: enabled
   - Environment:
     - `OPPORTUNITY_OS_API_ORIGIN=https://<your-api-service>.up.railway.app`

2. `opportunityos-api`
   - Dockerfile path: `apps/api/Dockerfile`
   - Public domain: enabled
   - Environment:
     - `OPPORTUNITY_OS_DATABASE_URL=${{Postgres.DATABASE_URL}}`
     - `REDIS_URL=${{Redis.REDIS_URL}}`
     - `OPPORTUNITY_OS_TASK_QUEUE=celery`
     - `OPPORTUNITY_OS_AUTH_SECRET=<generate-a-long-random-secret>`
     - `OPPORTUNITY_OS_SECURE_COOKIES=true`
     - `OPPORTUNITY_OS_COOKIE_SAMESITE=lax`
     - `OPPORTUNITY_OS_CORS_ORIGINS=https://<your-web-service>.up.railway.app`
     - `OPPORTUNITY_OS_ADMIN_EMAILS=<your-admin-email>`
     - Optional AI provider keys: `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `ZHIPU_API_KEY`

3. `opportunityos-worker`
   - Dockerfile path: `apps/api/Dockerfile`
   - Public domain: disabled
   - Start command:
     ```bash
     celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=${OPPORTUNITY_OS_SEARCH_WORKERS:-2}
     ```
   - Environment:
     - `OPPORTUNITY_OS_DATABASE_URL=${{Postgres.DATABASE_URL}}`
     - `REDIS_URL=${{Redis.REDIS_URL}}`
     - `OPPORTUNITY_OS_TASK_QUEUE=celery`
     - `OPPORTUNITY_OS_AUTH_SECRET=<same-secret-as-api>`
     - Same optional AI/source keys as the API service

Also add Railway managed services:

- PostgreSQL
- Redis

## Important

- Do not commit `.env` or API keys.
- The web service should call the API through `OPPORTUNITY_OS_API_ORIGIN`.
- The browser still uses same-origin `/api/*`, so cookies stay on the web domain.
- The worker must share the same database, Redis, and auth secret as the API.

## Useful URLs

- App: `https://<your-web-service>.up.railway.app`
- Admin: `https://<your-web-service>.up.railway.app/admin`
- Settings: `https://<your-web-service>.up.railway.app/settings`
