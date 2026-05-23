# Perceptr

Backend API for Perceptr — session recording ingestion, AI-powered UX analysis, issue detection, and analytics. Built with FastAPI, PostgreSQL, LangGraph, and AWS S3/SQS.

## Features

- Organization auth (JWT)
- rrweb session recording upload and analysis
- AI session analysis (OpenAI / Gemini via LangGraph)
- UX audit pipeline with PDF report generation
- Real-time WebSocket ingestion
- Analytics and issue tracking
- Email notifications via Brevo

## Prerequisites

- Python 3.11–3.13
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker & Docker Compose (optional, recommended for local/prod)
- AWS account with S3 bucket and SQS queue (for recordings storage and async processing)
- API keys: OpenAI, Gemini, Langfuse, Brevo

## Quick Start

### 1. Clone and install

```bash
git clone <repository-url>
cd perceptr
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values. See [.env.example](.env.example) for all variables. At minimum you need:

- `DATABASE_URL`
- `SECRET_KEY` and `REFRESH_SECRET_KEY` (generate with `openssl rand -hex 32`)
- `OPENAI_API_KEY`, `GEMINI_API_KEY`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_PRIVATE_KEY`, `LANGFUSE_HOST`
- `BREVO_API_KEY`
- AWS credentials and `SQS_QUEUE_URL` if using recording analysis

### 3. Database

```bash
createdb perceptr
uv run alembic upgrade head
```

### 4. Run locally

```bash
uv run python main.py
```

API: `http://localhost:8000`  
Health check: `GET /health`  
OpenAPI docs: `http://localhost:8000/docs`

Or with uvicorn directly:

```bash
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Docker (local)

Runs the API behind Caddy with a local TLS certificate:

```bash
cp .env.example .env
# fill in .env
docker compose up --build
```

API is available at `https://localhost` (Caddy uses `tls internal` for local dev).

## Production Deployment (Hostinger VPS)

Production runs on a **Hostinger VPS** using Docker Compose and Caddy for HTTPS.

### Stack

- `docker-compose.prod.yml` — API + Caddy reverse proxy
- `caddy/prod/Caddyfile` — set your domain (e.g. `api.example.com`)
- `.github/workflows/deploy-hostinger.yml` — GitHub Actions deploy via [Hostinger deploy-on-vps](https://github.com/hostinger/deploy-on-vps)

### Manual deploy on VPS

```bash
# On the VPS, with .env or exported variables set:
docker compose -f docker-compose.prod.yml up -d --build
```

### Run migrations on VPS

```bash
docker compose -f docker-compose.prod.yml exec api uv run alembic upgrade head
```

### View logs

```bash
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f caddy
```

### GitHub Actions deploy

Configure these repository secrets (and a `prod` environment if used):

| Secret | Description |
|--------|-------------|
| `HOSTINGER_API_KEY` | Hostinger API key |
| `HOSTINGER_VM_ID` | Target VPS ID |
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY`, `REFRESH_SECRET_KEY` | JWT signing keys |
| `OPENAI_API_KEY`, `GEMINI_API_KEY` | AI providers |
| `LANGFUSE_*` | Langfuse observability |
| `BREVO_API_KEY` | Email provider |
| `AWS_*`, `SQS_QUEUE_URL` | S3/SQS for recordings |

Enable deploy by uncommenting the branch trigger in `.github/workflows/deploy-hostinger.yml`.

> **Note:** `.github/workflows/cicd-pipeline.yml` is a legacy AWS ECS pipeline and is disabled. Production uses Hostinger VPS only.

## API Overview

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/orgs/signup` | Create organization |
| POST | `/api/v1/orgs/login` | Login (JSON) |
| POST | `/api/v1/orgs/token` | OAuth2 token endpoint |
| GET | `/api/v1/orgs/me` | Current org profile |

### Other modules

- `/api/v1/recording` — session recordings
- `/api/v1/recording-intervals` — recording chunks
- `/api/v1/issue` — detected issues
- `/api/v1/analytics` — analytics
- `/api/v1/chat`, `/api/v1/chat-message` — chat
- `/api/v1/uxaudit` — UX audit requests
- `/api/v1/email` — contact/demo emails
- `/api/v1/ws` — WebSocket ingestion
- `/api/v1/per` — SDK endpoints

See `/docs` for the full OpenAPI schema.

### Example: signup and login

```bash
curl -X POST http://localhost:8000/api/v1/orgs/signup \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "password": "your-password"}'

curl -X POST http://localhost:8000/api/v1/orgs/login \
  -H "Content-Type: application/json" \
  -d '{"email": "john@example.com", "password": "your-password"}'
```

## Email (Brevo)

Contact and notification emails use [Brevo](https://www.brevo.com/) transactional templates. Configure:

- `BREVO_INTERNAL_TO_EMAIL` — where inbound contact/lead emails are sent
- `BREVO_INTERNAL_CC_EMAILS` — optional comma-separated CC list
- `BREVO_INTERNAL_BCC_EMAILS` — optional comma-separated BCC list

Template IDs are hardcoded in `api/v1/email/` and `api/v1/uxaudit/service.py` — update them to match your Brevo account.

## Development

### Reset migrations (destructive)

```bash
dropdb perceptr && createdb perceptr
rm -f alembic/versions/*
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
```

### Tests

```bash
uv run python tests/test_api.py
```

## Security

Do not commit `.env` or real credentials. See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## License

[MIT](LICENSE)
