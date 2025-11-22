# Dockerization Roadmap

1. **Base Image**
   - Create `Dockerfile` using official `python:3.11-slim`.
   - Copy project source, install dependencies with `pip install -r requirements.txt`.
   - Expose environment variables for `DATABASE_URL`, defaulting to SQLite file mounted as volume.

2. **Compose Setup**
   - Author `docker-compose.yml` with services:
     - `web`: Flask app container using the base image.
     - `worker`: background job processor sharing the same image.
     - `cache`: Redis for task queue coordination (optional in early stages).
   - Mount local source for rapid iteration (`volumes: - ../:/app` during development).
   - Map ports (`web` -> 5000) and share `.env.docker` for configuration.

3. **SQLite to PostgreSQL Transition**
   - Provide optional `postgres` service in Compose with persistent volume.
   - Use env flag (e.g., `USE_POSTGRES=true`) to switch `DATABASE_URL` to Postgres DSN.
   - Document migration steps (`alembic upgrade head`) when toggling databases.

4. **Production Considerations**
   - Build optimized image with multi-stage build (dependencies then runtime).
   - Integrate health checks, logging configuration, and non-root user.
   - Publish image to container registry alongside IaC templates.
