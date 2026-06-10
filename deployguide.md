# 🚀 DialEasypro Deployment Guide for AWS

This guide provides step-by-step instructions to deploy the **DialEasypro** project on AWS EC2 with an RDS PostgreSQL database.

---

## **1. Infrastructure Overview**
- **Instance IP:** `43.204.108.197` (Ubuntu)
- **Database (RDS):** `database-1.chma0yqo49k7.ap-south-1.rds.amazonaws.com`
- **DB Name:** `default`
- **DB User:** `postgres` (Assumed default for RDS)
- **DB Password:** `Shiwansh123`
- **Stack:** Docker, Nginx, Django, Redis, Celery.

---

## **2. Prerequisites**
Before starting, ensure you have:
1. SSH access to the EC2 instance:
   ```bash
   ssh -i C:\Users\easyian\keys\pro.pem ubuntu@43.204.108.197
   ```
2. **DNS Record:** Point `api.dialeasypro.easyian.com` to your instance IP `43.204.108.197`.
3. **RDS Security Group:** Ensure the RDS security group allows **Inbound TCP traffic on port 5432** from the EC2 instance's Private IP or Security Group.

---

## **3. Server Preparation**
Once logged into your EC2 instance, run the following:

### **Update System & Install Docker (Official Script)**
If the previous installation failed, run this official script to install the latest Docker and Docker Compose:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Apply group changes
newgrp docker 
```

### **Verify Installation**
Ensure both commands return a version:
```bash
docker --version
docker compose version
```
*Note: If `docker compose version` fails, the script didn't install the plugin. You can install it manually: `sudo apt install docker-compose-plugin`.*


---

## **4. RDS Database Initialization**
Before the app can connect, you must manually create the database named `default` inside your RDS instance.

### **Connect to RDS**
```bash
# Connect using the master 'postgres' user
psql -h database-1.chma0yqo49k7.ap-south-1.rds.amazonaws.com -U postgres -d postgres
```
*Note: It will prompt for your password (Shiwansh123).*

### **Create the Application Database**
Run this SQL command inside the psql prompt:
```sql
CREATE DATABASE "default";
\q
```

---

## **5. Project Setup**

### **Clone the Repository**
```bash
git clone https://github.com/Shiwa45/Dialeasypro.git
cd Dialeasypro
```

### **Check Docker Compose Version**
Try both commands to see which one is active:
```bash
docker compose version
# OR
docker-compose version
```
*Note: If `docker compose` (with space) fails with a flag error, use `docker-compose` (with hyphen) instead.*

### **Configure Environment Variables**
Create a `.env` file in the root directory:
```bash
nano .env
```
Copy and paste the following, replacing placeholders with your actual secrets:

```env
# --- Django Settings ---
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=generate_a_strong_random_secret_key_here
DEBUG=False
ALLOWED_HOSTS=43.204.108.197,api.dialeasypro.easyian.com  # Added your API domain

# --- Database (RDS) ---
DB_NAME=default
DB_USER=postgres
DB_PASSWORD=Shiwansh123
DB_HOST=database-1.chma0yqo49k7.ap-south-1.rds.amazonaws.com
DB_PORT=5432
DB_SSLMODE=require

# --- Redis (Local Docker) ---
REDIS_PASSWORD=Shiwansh@123
REDIS_HOST=redis
REDIS_URL=redis://:Shiwansh@123@redis:6379/0
CELERY_BROKER_URL=redis://:Shiwansh@123@redis:6379/1
CELERY_RESULT_BACKEND=redis://:Shiwansh@123@redis:6379/2

# --- Storage & Domain ---
BASE_DOMAIN=api.dialeasypro.easyian.com
USE_S3=False  # Set to True and add AWS_ACCESS_KEY if using S3
```
*Note: Ensure `DB_USER` matches your RDS master username (usually `postgres`).*

---

## **6. Deployment with Docker**

### **Build and Start Services**
Use the command that worked in the previous step (with or without hyphen):
```bash
sudo docker-compose -f docker-compose.prod.yml up -d --build
```
*Note: Added `sudo` to ensure permissions and used `docker-compose` for better compatibility.*

### **Verify Running Containers**
```bash
docker ps
```
You should see: `telecrm_web`, `telecrm_redis`, `telecrm_celery_worker`, `telecrm_celery_beat`, and `telecrm_nginx`.

---

## **8. Post-Deployment Tasks**

### **Verify Running Containers**
```bash
sudo docker-compose -f docker-compose.prod.yml ps
```

### **Run Migrations**
Since the project uses `django-tenants`, you must run:
```bash
sudo docker exec -it telecrm_web python manage.py migrate_schemas --shared
```

### **Create Public Tenant**
You need a public tenant for the main domain:
```bash
sudo docker exec -it telecrm_web python manage.py create_public_tenant --domain api.dialeasypro.easyian.com --name "Public"
```

### **Seed Initial Data**
This command sets up plans, features, and the superadmin user:
```bash
sudo docker exec -it telecrm_web python manage.py setup_initial_data
```

### **Seed Call Dispositions**
Seed for the public schema (or use `--all` to seed for all existing tenants):
```bash
sudo docker exec -it telecrm_web python manage.py seed_dispositions --schema=public
```

### **Create Superuser (Optional)**
If you didn't create one via `setup_initial_data`, create one for the public schema:
```bash
sudo docker exec -it telecrm_web python manage.py createsuperuser --schema=public
```

---

## **8. Nginx Configuration (SSL)**
To enable HTTPS and serve only the Django API, update your Nginx config.

### **Install Certbot**
```bash
sudo apt install -y certbot python3-certbot-nginx
```

### **Configure Host Nginx**
Create a new configuration file on your host:
```bash
sudo nano /etc/nginx/sites-available/telecrm
```
Paste this configuration (Proxying to the Docker container on port 8000):
```nginx
server {
    listen 80;
    server_name api.dialeasypro.easyian.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/ubuntu/Dialeasypro/staticfiles/;
    }

    location /media/ {
        alias /home/ubuntu/Dialeasypro/mediafiles/;
    }
}
```
*Note: The `X-Forwarded-Proto $scheme` header is critical to prevent redirect loops.*

### **Enable SSL**
Run Certbot to automatically fetch and configure the SSL certificate:
```bash
sudo certbot --nginx -d api.dialeasypro.easyian.com
```

---

## **9. Troubleshooting**
- **DB Connection Error:** Check RDS Security Group Inbound rules (Port 5432).
- **Static Files Missing:** Run `sudo docker exec -it telecrm_web python manage.py collectstatic --no-input`.
- **Logs:** Use `sudo docker-compose -f docker-compose.prod.yml logs -f web` to debug backend issues.

---
**Guide Generated on:** 2026-06-10
**Author:** Trae AI Assistant
