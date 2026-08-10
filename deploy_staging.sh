#!/bin/bash
# Staging Deployment Script for Neighbor Service (ns_backend)
# Mirrors deploy_ultimate.sh for the staging/QA environment.
# Key differences from production:
#   - Single daphne instance (port 7100) — no replicas
#   - No PostgreSQL read-replica setup
#   - Cloudflare Origin Certificate (same as production) instead of Let's Encrypt
#   - Celery concurrency capped at 2 workers
#   - Encrypted backups retained for 7 days (vs 30 in production)
#   - Separate staging database (nsapp_staging)
#   - DJANGO_ENV=staging injected into all supervisor processes
# Usage: sudo bash deploy_staging.sh

set -e  # Exit on error

echo "========================================="
echo "Neighbor Service Staging Deployment"
echo "========================================="
echo ""

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
APP_NAME="ns_backend_staging"
APP_DIR="/opt/ns_backend_staging"
VENV_DIR="$APP_DIR/venv"
USER="afari"
GROUP="www-data"
APP_PORT=7100               # Single daphne instance
CELERY_CONCURRENCY=2
BACKUP_RETENTION_DAYS=7

# Staging database (isolated from production nsapp)
STAGING_DB_NAME="nsapp_staging"
STAGING_DB_USER="afari"             # reuse same OS user as production
STAGING_DB_PASSWORD="gentechco"     # update if you prefer a distinct staging password

# Staging domain — update before running
STAGING_DOMAIN="staging.neighborservice.com"
STAGING_API_DOMAIN="api.staging.neighborservice.com"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ─────────────────────────────────────────────
# Root check
# ─────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# ─────────────────────────────────────────────
# Interactive configuration
# ─────────────────────────────────────────────
echo -e "${BLUE}=== Staging Configuration ===${NC}"
echo ""

echo -e "${YELLOW}1. Staging domain (main site)${NC}"
read -p "   Enter staging domain [$STAGING_DOMAIN]: " INPUT_DOMAIN
[ -n "$INPUT_DOMAIN" ] && STAGING_DOMAIN="$INPUT_DOMAIN"

echo ""
echo -e "${YELLOW}2. Staging API subdomain${NC}"
read -p "   Enter API domain [$STAGING_API_DOMAIN]: " INPUT_API_DOMAIN
[ -n "$INPUT_API_DOMAIN" ] && STAGING_API_DOMAIN="$INPUT_API_DOMAIN"

echo ""
echo -e "${YELLOW}3. Email for Let's Encrypt certificate notifications${NC}"
read -p "   Enter email [$STAGING_EMAIL]: " INPUT_EMAIL
[ -n "$INPUT_EMAIL" ] && STAGING_EMAIL="$INPUT_EMAIL"

echo ""
echo -e "${YELLOW}4. Set up automated encrypted backups?${NC}"
echo "   1) Yes - Configure daily encrypted backups with $BACKUP_RETENTION_DAYS day retention"
echo "   2) No  - Skip backup configuration"
read -p "   Enter choice [1-2]: " BACKUP_CHOICE

echo ""
echo -e "${YELLOW}5. Set up .env configuration?${NC}"
echo "   Your .env file must contain staging-specific values."
if [ ! -f "$APP_DIR/.env" ]; then
    echo -e "${RED}   ⚠ No .env found at $APP_DIR/.env${NC}"
    echo "   Copy .env and fill in staging values:"
    echo "     cp $APP_DIR/.env $APP_DIR/.env && nano $APP_DIR/.env"
    read -p "   Press ENTER once .env is ready, or Ctrl+C to abort: "
else
    echo -e "${GREEN}   ✓ .env found at $APP_DIR/.env${NC}"
fi

echo ""
echo "   Summary:"
echo "   ─────────────────────────────────────────────"
echo "   App directory  : $APP_DIR"
echo "   Main domain    : $STAGING_DOMAIN"
echo "   API domain     : $STAGING_API_DOMAIN"
echo "   App port       : $APP_PORT"
echo "   Database       : $STAGING_DB_NAME"
echo "   SSL            : Cloudflare Origin Certificate"
echo "   ─────────────────────────────────────────────"
echo ""
read -p "   Proceed with staging deployment? [y/N]: " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# ─────────────────────────────────────────────
# Phase 1: System Setup
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo "Phase 1: System Setup"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 1: Installing system dependencies...${NC}"

apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    postgresql-18 \
    postgresql-contrib-18 \
    redis-server \
    nginx \
    supervisor \
    git \
    curl \
    cron \
    openssl

# Certbot not needed — using Cloudflare Origin Certificate

echo -e "${GREEN}✓ System dependencies installed${NC}"

echo -e "${YELLOW}Step 2: Creating application directory...${NC}"
mkdir -p $APP_DIR
mkdir -p $APP_DIR/logs
mkdir -p $APP_DIR/staticfiles
mkdir -p $APP_DIR/media
mkdir -p $APP_DIR/backups/postgres
echo -e "${GREEN}✓ Directories created${NC}"

echo -e "${YELLOW}Step 3: Setting up Python virtual environment...${NC}"
python3 -m venv $VENV_DIR
source $VENV_DIR/bin/activate
echo -e "${GREEN}✓ Virtual environment created${NC}"

echo -e "${YELLOW}Step 4: Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn daphne uvicorn[standard] django-redis django-tinymce
echo -e "${GREEN}✓ Python dependencies installed${NC}"

# ─────────────────────────────────────────────
# Phase 2: Database Setup
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo "Phase 2: Database Setup"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 5: Setting up PostgreSQL staging database...${NC}"

sudo -u postgres /usr/lib/postgresql/18/bin/psql -c \
    "CREATE DATABASE $STAGING_DB_NAME;" 2>/dev/null || \
    echo "   (Database $STAGING_DB_NAME already exists — skipping)"

sudo -u postgres /usr/lib/postgresql/18/bin/psql -c \
    "CREATE USER $STAGING_DB_USER WITH PASSWORD '$STAGING_DB_PASSWORD';" 2>/dev/null || \
    echo "   (User $STAGING_DB_USER already exists — skipping)"

sudo -u postgres /usr/lib/postgresql/18/bin/psql -c \
    "GRANT ALL PRIVILEGES ON DATABASE $STAGING_DB_NAME TO $STAGING_DB_USER;"

# PostgreSQL 15+: explicit schema ownership required
sudo -u postgres /usr/lib/postgresql/18/bin/psql -d $STAGING_DB_NAME -c \
    "ALTER SCHEMA public OWNER TO $STAGING_DB_USER;"

echo -e "${GREEN}✓ Staging database configured${NC}"

# ─────────────────────────────────────────────
# Optional: Encrypted Automated Backups
# ─────────────────────────────────────────────
if [ "$BACKUP_CHOICE" = "1" ]; then
    echo ""
    echo -e "${YELLOW}Step 6: Setting up automated encrypted backups...${NC}"

    # Generate encryption key if it doesn't exist
    BACKUP_KEY_FILE="$APP_DIR/backup_key.bin"
    if [ ! -s "$BACKUP_KEY_FILE" ]; then
        echo -e "${YELLOW}   Generating backup encryption key...${NC}"
        head -c 32 /dev/urandom | base64 > "$BACKUP_KEY_FILE"
        chmod 600 "$BACKUP_KEY_FILE"
        chown root:root "$BACKUP_KEY_FILE"
        echo -e "${GREEN}   ✓ Encryption key generated at $BACKUP_KEY_FILE${NC}"
        echo -e "${RED}   IMPORTANT: Save this key securely — you cannot decrypt backups without it!${NC}"
    else
        echo -e "${GREEN}   ✓ Existing encryption key found at $BACKUP_KEY_FILE${NC}"
    fi

    cat > $APP_DIR/backup_postgres.sh << 'BACKUP_SCRIPT'
#!/bin/bash
# Automated Encrypted PostgreSQL backup script (staging)
APP_DIR="/opt/ns_backend_staging"
BACKUP_DIR="$APP_DIR/backups/postgres"
BACKUP_KEY_FILE="$APP_DIR/backup_key.bin"
DB_NAME="nsapp_staging"
RETENTION_DAYS=7
DATE=$(date +%Y%m%d_%H%M%S)
TEMP_FILE="$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz"
ENC_FILE="$TEMP_FILE.enc"

mkdir -p $BACKUP_DIR

echo "Starting backup for $DB_NAME..."
sudo -u postgres pg_dump $DB_NAME | gzip > $TEMP_FILE

if [ $? -eq 0 ]; then
    echo "Encrypting backup..."
    openssl enc -aes-256-cbc -salt -in $TEMP_FILE -out $ENC_FILE \
        -pass file:"$BACKUP_KEY_FILE" -pbkdf2

    if [ $? -eq 0 ]; then
        echo "✓ Backup completed and encrypted: $ENC_FILE"
        rm -f $TEMP_FILE
        find $BACKUP_DIR -name "*.sql.gz*" -type f -mtime +$RETENTION_DAYS -delete
    else
        echo "✗ Encryption failed!"
        exit 1
    fi
else
    echo "✗ Backup failed!"
    exit 1
fi
BACKUP_SCRIPT

    chmod +x $APP_DIR/backup_postgres.sh
    chown root:root $APP_DIR/backup_postgres.sh

    # Daily at 3 AM — offset from production (2 AM) to avoid I/O conflicts
    (crontab -l 2>/dev/null | grep -v "backup_postgres.sh"; \
        echo "0 3 * * * $APP_DIR/backup_postgres.sh >> $APP_DIR/logs/backup.log 2>&1") | crontab -

    echo -e "${GREEN}✓ Automated encrypted backups configured (daily at 3 AM, $BACKUP_RETENTION_DAYS day retention)${NC}"
fi

# ─────────────────────────────────────────────
# Phase 3: Django Setup
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo "Phase 3: Django Setup"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 7: Running migrations and collecting static files...${NC}"
source $VENV_DIR/bin/activate
cd $APP_DIR

python manage.py migrate --noinput
echo -e "${GREEN}  ✓ Migrations applied${NC}"

python manage.py collectstatic --noinput
echo -e "${GREEN}✓ Static files collected${NC}"

# ─────────────────────────────────────────────
# Phase 4: Supervisor (single daphne + celery)
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo "Phase 4: Supervisor Configuration"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 8: Writing Supervisor configuration (1 app instance + Celery)...${NC}"

cat > /etc/supervisor/conf.d/$APP_NAME.conf << EOF
; ─── Neighbor Service Staging ───────────────────────────────────────────────

[program:${APP_NAME}_app]
command=$VENV_DIR/bin/daphne -b 127.0.0.1 -p $APP_PORT --access-log - --proxy-headers ns_backend.asgi:application
directory=$APP_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$APP_DIR/logs/daphne.log
environment=PATH="$VENV_DIR/bin",DJANGO_ENV="staging"

[program:${APP_NAME}_celery]
command=$VENV_DIR/bin/celery -A ns_backend worker -l info --concurrency=$CELERY_CONCURRENCY
directory=$APP_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$APP_DIR/logs/celery.log
environment=PATH="$VENV_DIR/bin",DJANGO_ENV="staging"

[program:${APP_NAME}_celery_beat]
command=$VENV_DIR/bin/celery -A ns_backend beat -l info
directory=$APP_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$APP_DIR/logs/celery-beat.log
environment=PATH="$VENV_DIR/bin",DJANGO_ENV="staging"

[group:${APP_NAME}_all]
programs=${APP_NAME}_app,${APP_NAME}_celery,${APP_NAME}_celery_beat
EOF

supervisorctl reread
supervisorctl update
echo -e "${GREEN}✓ Supervisor configured${NC}"

# ─────────────────────────────────────────────
# Phase 5: Nginx + Cloudflare SSL
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo "Phase 5: Nginx & Cloudflare SSL"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 9: Setting up Cloudflare Origin Certificate...${NC}"

mkdir -p /etc/ssl/cloudflare
chmod 755 /etc/ssl/cloudflare

# if [ ! -s /etc/ssl/cloudflare/origin.pem ] || [ ! -s /etc/ssl/cloudflare/origin-key.pem ]; then
    echo ""
    echo "========================================="
    echo "Cloudflare Origin Certificate Setup"
    echo "========================================="
    echo ""
    echo "Please follow these steps in the Cloudflare Dashboard:"
    echo "1. Go to SSL/TLS → Origin Server"
    echo "2. Click 'Create Certificate'"
    echo "3. Hostnames: $STAGING_DOMAIN, *.$STAGING_DOMAIN"
    echo "4. Validity: 15 years"
    echo "5. Click 'Create'"
    echo ""
    echo -e "${YELLOW}Paste the Origin Certificate below and press Ctrl+D when done:${NC}"
    cat > /etc/ssl/cloudflare/origin.pem

    echo ""
    echo -e "${YELLOW}Paste the Private Key below and press Ctrl+D when done:${NC}"
    cat > /etc/ssl/cloudflare/origin-key.pem

    chmod 644 /etc/ssl/cloudflare/origin.pem
    chmod 600 /etc/ssl/cloudflare/origin-key.pem

    echo -e "${GREEN}✓ Cloudflare certificates saved${NC}"
# fi

echo -e "${YELLOW}Step 10: Writing Nginx config (Cloudflare SSL)...${NC}"

cat > /etc/nginx/sites-available/$APP_NAME << EOF
# ─── Neighbor Service Staging Nginx ─────────────────────────────────────────

upstream ns_staging_backend {
    server 127.0.0.1:$APP_PORT;
}

# WebSocket Upgrade Map
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      close;
}

# Redirect HTTP → HTTPS
server {
    listen 80;
    server_name $STAGING_DOMAIN $STAGING_API_DOMAIN;
    return 301 https://\$host\$request_uri;
}

# ── 1. API Subdomain ──────────────────────────────────────────────────────────
server {
    listen 443 ssl http2;
    server_name $STAGING_API_DOMAIN;

    ssl_certificate     /etc/ssl/cloudflare/origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/origin-key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;

    # Cloudflare Real IP
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 172.64.0.0/13;
    real_ip_header CF-Connecting-IP;

    client_max_body_size 100M;

    # Staging environment identifier
    add_header X-Environment "staging" always;

    # Block admin access via API subdomain
    location /admin {
        return 404;
    }

    location /static/ {
        alias $APP_DIR/staticfiles/;
    }

    location /media/ {
        alias $APP_DIR/media/;
        add_header Access-Control-Allow-Origin *;
    }

    location /ws/ {
        proxy_pass http://ns_staging_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_read_timeout 86400;
    }

    location /api/ {
        proxy_pass http://ns_staging_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_connect_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /api {
        return 301 https://$STAGING_API_DOMAIN/api/;
    }

    location /callbacks/ {
        proxy_pass http://ns_staging_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location / {
        return 301 https://$STAGING_DOMAIN\$request_uri;
    }

    access_log $APP_DIR/logs/nginx-api-access.log;
    error_log  $APP_DIR/logs/nginx-api-error.log warn;
}

# ── 2. Main Staging Site ──────────────────────────────────────────────────────
server {
    listen 443 ssl http2;
    server_name $STAGING_DOMAIN;

    ssl_certificate     /etc/ssl/cloudflare/origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/origin-key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;

    # Cloudflare Real IP
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 172.64.0.0/13;
    real_ip_header CF-Connecting-IP;

    client_max_body_size 100M;

    add_header X-Environment "staging" always;

    location /static/ {
        alias $APP_DIR/staticfiles/;
    }

    location /media/ {
        alias $APP_DIR/media/;
    }

    location /ws/ {
        proxy_pass http://ns_staging_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_read_timeout 86400;
    }

    location / {
        proxy_pass http://ns_staging_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        proxy_redirect off;
    }

    access_log $APP_DIR/logs/nginx-access.log;
    error_log  $APP_DIR/logs/nginx-error.log warn;
}
EOF

ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Nginx configuration is valid${NC}"
    systemctl restart nginx
    echo -e "${GREEN}✓ Nginx restarted${NC}"
else
    echo -e "${RED}✗ Nginx configuration has errors — please check manually${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Cloudflare SSL configured — certificates are valid for 15 years${NC}"

# ─────────────────────────────────────────────
# Phase 6: Permissions & Start Services
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo "Phase 6: Permissions & Services"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 12: Setting permissions...${NC}"
chown -R $USER:$GROUP $APP_DIR
chmod -R 755 $APP_DIR
chown -R $USER:$GROUP $APP_DIR/media
chmod -R 775 $APP_DIR/media
chown -R $USER:$GROUP $APP_DIR/staticfiles
chmod -R 755 $APP_DIR/staticfiles
chmod -R 775 $APP_DIR/logs
chmod -R 775 $APP_DIR/backups
# Keep backup key root-owned for security
[ -f "$APP_DIR/backup_key.bin" ] && chown root:root "$APP_DIR/backup_key.bin" && chmod 600 "$APP_DIR/backup_key.bin"
echo -e "${GREEN}✓ Permissions set${NC}"

echo -e "${YELLOW}Step 13: Starting services...${NC}"

# Kill any stray daphne/gunicorn processes on staging port
pkill -f "daphne.*$APP_PORT" || true

systemctl enable redis-server
systemctl start redis-server

supervisorctl reread
supervisorctl update
supervisorctl restart ${APP_NAME}_all:*
echo -e "${YELLOW}Waiting for services to initialize...${NC}"
sleep 5
echo -e "${GREEN}✓ Services started${NC}"

# ─────────────────────────────────────────────
# Phase 7: Data Population
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo "Phase 7: Data Population"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 14: Checking for superuser...${NC}"
source $VENV_DIR/bin/activate
cd $APP_DIR
python manage.py create_superuser_if_none || echo "   Superuser check skipped or command not found"
echo -e "${GREEN}✓ Data population completed${NC}"

# ─────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────
echo ""
echo "========================================="
echo -e "${GREEN}🎉 Staging Deployment Complete!${NC}"
echo "========================================="
echo ""
echo -e "${CYAN}Application    :${NC} Neighbor Service (STAGING)"
echo -e "${CYAN}App instance   :${NC} 1  (port $APP_PORT)"
echo -e "${CYAN}Main URL       :${NC} https://$STAGING_DOMAIN"
echo -e "${CYAN}API URL        :${NC} https://$STAGING_API_DOMAIN"
echo -e "${CYAN}Database       :${NC} $STAGING_DB_NAME"
echo -e "${CYAN}SSL            :${NC} Cloudflare Origin Certificate ✓"
echo ""

if [ "$BACKUP_CHOICE" = "1" ]; then
    echo -e "${CYAN}Backups        :${NC} Daily at 3 AM, AES-256 encrypted ($BACKUP_RETENTION_DAYS day retention)"
    echo -e "${CYAN}Encryption key :${NC} $APP_DIR/backup_key.bin  ← back this up securely!"
fi

echo ""
echo "─────────────────────────────────────────────────"
echo "📋 Required .env values for staging:"
echo "─────────────────────────────────────────────────"
cat << 'ENVBLOCK'
DEBUG=False                                 # set True only for local QA sessions
SECRET_KEY=<unique-staging-secret-key>

DATABASE_NAME=nsapp_staging
DATABASE_USER=afari
DATABASE_PASSWORD=gentechco
DATABASE_HOST=localhost
DATABASE_PORT=5432

REDIS_URL=redis://127.0.0.1:6379/2         # DB index 2 — avoids collision with prod

ALLOWED_HOSTS=staging.neighborservice.com,api.staging.neighborservice.com
CORS_ALLOWED_ORIGINS=https://staging.neighborservice.com

# Update to your staging domain
DOMAIN=staging.neighborservice.com
ENVBLOCK

echo ""
echo "─────────────────────────────────────────────────"
echo "📊 Management Commands:"
echo "─────────────────────────────────────────────────"
echo "  Status           : sudo supervisorctl status"
echo "  Restart app      : sudo supervisorctl restart ${APP_NAME}_app"
echo "  Restart all      : sudo supervisorctl restart ${APP_NAME}_all:*"
echo "  App logs         : tail -f $APP_DIR/logs/daphne.log"
echo "  Celery logs      : tail -f $APP_DIR/logs/celery.log"
echo "  Nginx logs       : tail -f $APP_DIR/logs/nginx-access.log"
echo "  SSL cert        : /etc/ssl/cloudflare/origin.pem (15-year Cloudflare Origin Cert)"
echo ""
echo "  Create superuser :"
echo "    cd $APP_DIR && source venv/bin/activate && python manage.py createsuperuser"
echo ""

if [ "$BACKUP_CHOICE" = "1" ]; then
    echo "  Manual backup    : $APP_DIR/backup_postgres.sh"
    echo "  View backups     : ls -lh $APP_DIR/backups/postgres/"
    echo "  Decrypt backup   : openssl enc -aes-256-cbc -d -salt -pbkdf2 \\"
    echo "                       -in <file>.enc -out <file>.gz -pass file:$APP_DIR/backup_key.bin"
    echo ""
fi

echo "🚀 Neighbor Service staging is live!"
echo "   Main : https://$STAGING_DOMAIN"
echo "   API  : https://$STAGING_API_DOMAIN"
echo ""
