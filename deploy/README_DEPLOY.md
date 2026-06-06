# Deployment Guide

This repository supports a production deployment on an Ubuntu server using Docker Compose.

## Prerequisites
- Ubuntu server with `sudo` access
- Docker installed
- Docker Compose plugin installed
- Public IP or DNS pointing to the server
- AWS RDS PostgreSQL host and credentials
- Optional: AWS S3 credentials if `USE_S3=True`

## Production Environment
Copy the example file and fill in the values:

```bash
cd /home/ubuntu/DialEasypro
cp deploy/prod.env.example .env
# edit .env and replace values
```

Key values to set:
- `SECRET_KEY` — strong random string
- `DB_PASSWORD` — the RDS password for your database user
- `DB_HOST` — `database-1.cleiw2sogobg.eu-north-1.rds.amazonaws.com`
- `REDIS_PASSWORD` — password for Redis running on the server
- `ALLOWED_HOSTS` — set to the server IP or domain
- `USE_S3` — set to `False` if you are not using S3 yet

## Deploying on the Ubuntu Server

1. Clone the repository:
```bash
cd /home/ubuntu
git clone https://github.com/Shiwa45/Dialeasypro.git
cd Dialeasypro
```

2. Create the production env file:
```bash
cp deploy/prod.env.example .env
# edit .env with your secrets, especially SECRET_KEY and DB_PASSWORD
```

3. Start the production stack:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

4. Verify the services:
```bash
docker compose -f docker-compose.prod.yml ps
```

## Notes
- The app uses the external RDS instance defined by `DB_HOST`.
- Redis is deployed locally in Docker on the server.
- If you want to expose the backend on port 80, the production Compose file includes an Nginx proxy.
- Do not commit `.env` to GitHub; it is excluded by `.gitignore`.
