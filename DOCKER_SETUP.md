# Docker Setup Guide

## Quick Start

### 1. Prepare Environment Variables
Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

Update the `.env` file with:
- `DATABASE_URL` pointing to your external PostgreSQL database (self-hosted, NeonDB, or other service)
- SMTP credentials for email notifications
- `SPREADSHEET_ID` for Google Sheets integration

### 2. Start Backend Service
```bash
docker-compose up -d
```

This will build and start the FastAPI backend container connected to your external database.

### 3. Run Database Migrations (if needed)
If using a new database, run Alembic migrations:
```bash
docker-compose exec backend alembic upgrade head
```

### 4. Verify Service
```bash
# Check service status
docker-compose ps

# View backend logs
docker-compose logs backend
```

## Database Connection

The backend connects to an **external PostgreSQL database** specified by the `DATABASE_URL` environment variable.

Examples:
- **Self-hosted PostgreSQL on Linux server:** `postgresql+asyncpg://user:password@your-server-ip:5432/neondb`
- **NeonDB:** `postgresql://user:password@neon-host/dbname?sslmode=require`
- **Local machine:** `postgresql+asyncpg://user:password@localhost:5432/neondb`

## API Access

The FastAPI backend is available at `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Redoc: `http://localhost:8000/redoc`

## Common Commands

```bash
# Start backend
docker-compose up -d

# Stop backend (keep running external database)
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# View logs
docker-compose logs -f backend

# Access backend shell
docker-compose exec backend bash

# Run migrations
docker-compose exec backend alembic upgrade head
```

## Accessing via ngrok (later)

When ready to expose via ngrok, the backend will be accessible at `http://localhost:8000`. You can then use:
```bash
ngrok http 8000
```

## Troubleshooting

**Database connection issues:**
1. Verify `DATABASE_URL` in `.env` is correct
2. Ensure your external database is accessible from Docker
3. Check backend logs: `docker-compose logs backend`

**Port conflicts:**
If port 8000 is in use, modify the port mapping in `docker-compose.yml`.

**Migrations not applied:**
```bash
docker-compose exec backend alembic upgrade head
```
