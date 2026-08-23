# Production Deployment Guide: CareSync Healthcare Platform

This guide provides end-to-end production deployment instructions for the CareSync Healthcare Platform, covering Frontend static hosting, FastAPI backend services, MySQL database configuration, Redis caching, and Celery background workers.

---

## 1. Architecture Overview

```
                          [ Internet / Clients ]
                                    |
                                    v
                     [ Nginx Reverse Proxy / SSL ]
                      /                         \
                     v                           v
         [ Frontend Static Files ]       [ FastAPI Backend (Gunicorn) ]
         (HTML5/CSS3/Vanilla JS)          http://127.0.0.1:8000
                                                 |
                     +---------------------------+---------------------------+
                     |                           |                           |
                     v                           v                           v
            [ MySQL Database ]          [ Redis Queue:6379 ]        [ Google Cloud APIs ]
            (Relational Data)                    |                  (OAuth & Gemini LLM)
                                    +------------+------------+
                                    |                         |
                                    v                         v
                           [ Celery Worker ]          [ Celery Beat ]
                           (Async Tasks)              (Periodic Cron)
```

---

## 2. Server Prerequisites

- **OS**: Ubuntu 22.04 LTS / Debian 12 (or Windows Server 2022)
- **Python**: 3.10+
- **Database**: MySQL 8.0+ (or PostgreSQL 14+)
- **In-Memory Cache**: Redis 6.2+
- **Reverse Proxy**: Nginx 1.22+
- **Process Manager**: systemd / Supervisor

---

## 3. MySQL Database Setup

```bash
# 1. Access MySQL as root
sudo mysql -u root -p

# 2. Create production database & dedicated user
CREATE DATABASE healthcare_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'caresync_prod'@'localhost' IDENTIFIED BY 'StrongProductionPassword123!';
GRANT ALL PRIVILEGES ON healthcare_manager.* TO 'caresync_prod'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

---

## 4. Backend Service Deployment

### Step 1: Clone and Set Up Virtual Environment
```bash
# Clone repository into /var/www/
sudo mkdir -p /var/www/caresync
cd /var/www/caresync
git clone https://github.com/your-org/healthcare-appointment-manager.git .

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install production dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install gunicorn
```

### Step 2: Configure Production Environment Variables
Create `/var/www/caresync/backend/.env`:
```env
APP_NAME="CareSync Healthcare Appointment & Follow-up Manager"
APP_ENV=production
DEBUG=False
HOST=127.0.0.1
PORT=8000

CORS_ORIGINS=https://caresync.yourdomain.com

DATABASE_URL=mysql+pymysql://caresync_prod:StrongProductionPassword123!@localhost:3306/healthcare_manager

SECRET_KEY=9f82d8c3e8194a2b9f30e7195d8201a4e63b21890cf5a73e028b594821a0e194
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120

GEMINI_API_KEY=AIzaSyYourProductionGeminiKey
LLM_PROVIDER=gemini
LLM_MODEL_NAME=gemini-1.5-flash

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SG.yourProductionSendgridKey
SMTP_TLS=True
EMAIL_FROM=noreply@caresync.yourdomain.com
EMAIL_FROM_NAME=CareSync Health Alerts

GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-yourGoogleSecret
GOOGLE_REDIRECT_URI=https://caresync.yourdomain.com/api/calendar/callback
GOOGLE_CALENDAR_MODE=live
```

### Step 3: Run Database Migrations & Seed Baseline
```bash
cd /var/www/caresync/backend
# Initialize database tables
python -c "from app.database import init_db; init_db()"
```

### Step 4: Configure systemd for FastAPI Gunicorn
Create `/etc/systemd/system/caresync-api.service`:
```ini
[Unit]
Description=CareSync FastAPI Application
After=network.target mysql.service redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/caresync/backend
EnvironmentFile=/var/www/caresync/backend/.env
ExecStart=/var/www/caresync/venv/bin/gunicorn app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8000 \
    --access-logfile /var/log/caresync/api-access.log \
    --error-logfile /var/log/caresync/api-error.log

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 5. Celery Worker & Celery Beat Daemons

### Celery Background Worker
Create `/etc/systemd/system/caresync-celery-worker.service`:
```ini
[Unit]
Description=CareSync Celery Background Worker
After=network.target redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/caresync/backend
EnvironmentFile=/var/www/caresync/backend/.env
ExecStart=/var/www/caresync/venv/bin/celery -A app.tasks.celery_app worker --loglevel=INFO --concurrency=4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Celery Beat Periodic Scheduler
Create `/etc/systemd/system/caresync-celery-beat.service`:
```ini
[Unit]
Description=CareSync Celery Beat Periodic Scheduler
After=network.target redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/caresync/backend
EnvironmentFile=/var/www/caresync/backend/.env
ExecStart=/var/www/caresync/venv/bin/celery -A app.tasks.celery_app beat --loglevel=INFO
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 6. Nginx Web Server & Frontend Hosting

Create `/etc/nginx/sites-available/caresync`:
```nginx
server {
    listen 80;
    server_name caresync.yourdomain.com;

    # Redirect all HTTP traffic to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name caresync.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/caresync.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/caresync.yourdomain.com/privkey.pem;

    # Static Frontend root
    root /var/www/caresync/frontend;
    index index.html;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Frontend Static Routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Reverse Proxy to FastAPI Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90;
    }

    # Interactive API Documentation
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_set_header Host $host;
    }
}
```

Enable site and start services:
```bash
sudo ln -s /etc/nginx/sites-available/caresync /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

sudo systemctl daemon-reload
sudo systemctl enable --now caresync-api
sudo systemctl enable --now caresync-celery-worker
sudo systemctl enable --now caresync-celery-beat
```

---

## 7. Verification & Health Monitoring

```bash
# Check service statuses
sudo systemctl status caresync-api
sudo systemctl status caresync-celery-worker
sudo systemctl status caresync-celery-beat

# Verify API health endpoint
curl -I https://caresync.yourdomain.com/api/health
```
