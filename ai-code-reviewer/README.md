# AI-Powered Code Review Assistant

Automatically reviews GitHub Pull Requests using an LLM (Groq or local Ollama) and posts inline review comments directly on the diff. A React dashboard lets you track review history and issue metrics across all monitored repositories.

## Architecture

```
GitHub PR Event
      │  webhook POST /webhook/github
      ▼
Webhook Handler ──► Diff Parser ──► Review Engine ──► LLM (Groq / Ollama)
                                          │
                              ┌───────────┴────────────┐
                              ▼                        ▼
                       GitHub Client            PostgreSQL DB
                   (inline PR comments)              │
                                                Dashboard API
                                                      │
                                               React Frontend
```

**Stack:** FastAPI · SQLAlchemy (async) · Alembic · PostgreSQL 16 · React · Vite · Tailwind CSS · Recharts

---

## Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Docker Compose | v2 (bundled with Docker Desktop) |
| ngrok (for local webhook testing) | any recent version |

---

## Quick Start (Docker Compose)

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd ai-code-reviewer
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Variable | Description |
|----------|-------------|
| `GITHUB_WEBHOOK_SECRET` | Secret token used to validate GitHub webhook signatures. Generate one with `openssl rand -hex 32`. |
| `GITHUB_TOKEN` | Personal access token with `repo` scope, used to post inline review comments. Create one at [github.com/settings/tokens](https://github.com/settings/tokens). |
| `LLM_PROVIDER` | `groq` (default) or `ollama` |
| `GROQ_API_KEY` | Free API key from [console.groq.com](https://console.groq.com). Required when `LLM_PROVIDER=groq`. |
| `OLLAMA_BASE_URL` | Base URL for a running Ollama instance, e.g. `http://host.docker.internal:11434`. Only needed when `LLM_PROVIDER=ollama`. |
| `DATABASE_URL` | Pre-filled for Docker Compose: `postgresql+asyncpg://postgres:postgres@db:5432/code_reviewer`. Change only if you use an external database. |

### 3. Start all services

```bash
docker compose up --build
```

This starts three services:

| Service | URL | Description |
|---------|-----|-------------|
| `api` | http://localhost:8000 | FastAPI backend + auto-migration on startup |
| `db` | localhost:5432 | PostgreSQL 16 |
| `frontend` | http://localhost:5173 | Vite React dev server |

The backend automatically runs Alembic migrations before starting, so the database schema is always up to date.

### 4. Expose the webhook endpoint with ngrok

GitHub needs a public URL to deliver webhook events. In a separate terminal:

```bash
ngrok http 8000
```

Copy the `Forwarding` URL (e.g. `https://abc123.ngrok-free.app`).

### 5. Register the webhook on GitHub

1. Go to your GitHub repository → **Settings → Webhooks → Add webhook**
2. Set **Payload URL** to `https://<your-ngrok-url>/webhook/github`
3. Set **Content type** to `application/json`
4. Set **Secret** to the same value as `GITHUB_WEBHOOK_SECRET` in your `.env`
5. Under **Which events**, choose **Let me select individual events** and check **Pull requests**
6. Click **Add webhook**

### 6. Open the dashboard

Navigate to **http://localhost:5173** to see the review dashboard.

---

## How It Works

1. A PR is opened, synchronized, or reopened on a monitored repository.
2. GitHub delivers a `pull_request` webhook event to `POST /webhook/github`.
3. The backend validates the HMAC-SHA256 signature and dispatches a background review job.
4. The diff is parsed into structured hunks with ±20 lines of surrounding context fetched from the GitHub API.
5. Each hunk is sent to the LLM with a structured prompt requesting JSON feedback:
   - **category**: `security` | `architecture` | `performance` | `style` | `bug`
   - **severity**: `critical` | `warning` | `info`
   - **line**: exact diff line number
   - **comment**: explanation of the issue
   - **suggestion**: suggested fix
6. Feedback is posted as inline review comments on the PR via the GitHub API.
7. The review is persisted to PostgreSQL and surfaced in the React dashboard.

---

## Development

### Running without Docker

**Backend**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Start a local Postgres instance first, then:
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/code_reviewer
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

### Running tests

```bash
# Backend
cd backend && pytest

# Frontend
cd frontend && npm test
```

### Creating a new database migration

```bash
cd backend
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/github` | Receives GitHub webhook events |
| `GET` | `/api/repos` | List all tracked repositories |
| `GET` | `/api/repos/{repo}/reviews` | Paginated PR review history for a repo |
| `GET` | `/api/repos/{repo}/metrics` | Aggregated issue counts by category/severity |
| `GET` | `/api/reviews/{id}` | Full comment list for a single review |
| `GET` | `/health` | Health check |

Interactive API docs available at **http://localhost:8000/docs** (Swagger UI).

---

## Environment Variables Reference

See [`.env.example`](.env.example) for a complete, annotated list.

---

## Project Structure

```
ai-code-reviewer/
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh          # Runs migrations then starts uvicorn
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── alembic.ini
│   └── app/
│       ├── main.py            # FastAPI app & lifespan
│       ├── config.py          # Settings via pydantic-settings
│       ├── api/
│       │   ├── webhooks.py    # POST /webhook/github
│       │   └── dashboard.py   # Dashboard API routes
│       ├── core/
│       │   ├── diff_parser.py
│       │   ├── review_engine.py
│       │   └── llm/
│       │       ├── base.py
│       │       ├── groq_provider.py
│       │       └── ollama_provider.py
│       ├── github/
│       │   ├── client.py
│       │   └── webhook_validator.py
│       └── db/
│           ├── models.py
│           ├── session.py
│           └── migrations/
├── frontend/
│   ├── Dockerfile
│   ├── vite.config.ts
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx
│       │   ├── RepoDetail.tsx
│       │   └── ReviewDetail.tsx
│       ├── components/
│       │   ├── MetricCard.tsx
│       │   ├── IssueChart.tsx
│       │   └── ReviewTable.tsx
│       └── api/client.ts
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Troubleshooting

**`api` container exits immediately**
- Check that `.env` exists and `DATABASE_URL` points to `db:5432` (not `localhost`).
- Run `docker compose logs api` to see the full error.

**Webhook events not arriving**
- Confirm ngrok is running and the URL in the GitHub webhook settings matches the current ngrok forwarding URL (it changes on each ngrok restart unless you use a reserved domain).
- Check `docker compose logs api` for signature validation errors — make sure `GITHUB_WEBHOOK_SECRET` in `.env` matches the secret entered in GitHub.

**LLM not responding**
- For Groq: verify `GROQ_API_KEY` is valid and you haven't hit the free-tier rate limit.
- For Ollama: ensure the Ollama server is running and `OLLAMA_BASE_URL` is reachable from inside the container (use `http://host.docker.internal:11434` on macOS/Windows).

**Frontend can't reach the API**
- The Vite dev server proxies `/api` and `/webhook` to the `api` container via the `API_PROXY_TARGET` environment variable set in `docker-compose.yml`. Check `docker compose logs frontend` if requests are failing.
