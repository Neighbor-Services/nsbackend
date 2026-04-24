#!/bin/bash
# Ultimate Production Deployment Script for Puxbay
# Includes: Application + Cloudflare SSL + PostgreSQL Replicas + Automated Backups
# Usage: sudo bash deploy_ultimate.sh

set -e  # Exit on error

echo "========================================="
echo "Puxbay Ultimate Production Deployment"
echo "========================================="
echo ""

# Configuration
APP_NAME="puxbay"
APP_DIR="/opt/puxbay"
VENV_DIR="$APP_DIR/venv"
USER="softivite"
GROUP="www-data"
APP_REPLICAS=5
DB_REPLICAS=0
REPLICATION_USER="puxbay"
REPLICATION_PASSWORD="Thinkce@softivitepuxbay"
BACKUP_RETENTION_DAYS=30

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Interactive configuration
echo -e "${BLUE}=== Configuration ===${NC}"
echo ""
echo "Note: Cloudflare SSL will be configured automatically."
echo "Please have your Cloudflare Origin Certificate and Private Key ready."
echo ""

echo -e "${YELLOW}1. Do you want to set up PostgreSQL replication (5 replicas)?${NC}"
echo "   1) Yes - Set up 5 read replicas for high availability"
echo "   2) No - Skip replication setup"
read -p "   Enter choice [1-2]: " REPLICATION_CHOICE

# Export DB_NUM_REPLICAS for Django settings
if [ "$REPLICATION_CHOICE" = "1" ]; then
    export DB_NUM_REPLICAS=$DB_REPLICAS
else
    export DB_NUM_REPLICAS=0
fi

echo ""
echo -e "${YELLOW}2. Do you want to set up automated daily backups?${NC}"
echo "   1) Yes - Configure daily backups with $BACKUP_RETENTION_DAYS day retention"
echo "   2) No - Skip backup configuration"
read -p "   Enter choice [1-2]: " BACKUP_CHOICE

echo ""
echo "========================================="
echo "Phase 1: System Setup"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 1: Installing system dependencies...${NC}"

# Add PostgreSQL 18 repository
apt-get install -y wget ca-certificates gnupg lsb-release
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list

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
    cron

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

echo ""
echo "========================================="
echo "Phase 2: Database Setup"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 5: Setting up PostgreSQL primary database...${NC}"
# Using PostgreSQL 18 with explicit user/group (consistent with systemd service)
sudo -u postgres /usr/lib/postgresql/18/bin/psql -c "CREATE DATABASE puxbay;" || echo "Database already exists"
sudo -u postgres /usr/lib/postgresql/18/bin/psql -c "CREATE USER puxbay WITH PASSWORD 'Thinkce@softivitepuxbay';" || echo "User already exists"
sudo -u postgres /usr/lib/postgresql/18/bin/psql -c "GRANT ALL PRIVILEGES ON DATABASE puxbay TO puxbay;"
# Fix for PostgreSQL 15+: Grant creation rights on public schema
sudo -u postgres /usr/lib/postgresql/18/bin/psql -d puxbay -c "ALTER SCHEMA public OWNER TO puxbay;"

echo -e "${GREEN}✓ Primary database configured${NC}"

# PostgreSQL Replication Setup
if [ "$REPLICATION_CHOICE" = "1" ]; then
    echo ""
    echo -e "${YELLOW}Step 6: Setting up PostgreSQL replication ($DB_REPLICAS replicas)...${NC}"
    
    # Create replication user (using PostgreSQL 18 explicit path)
    sudo -u postgres /usr/lib/postgresql/18/bin/psql -c "CREATE USER $REPLICATION_USER WITH REPLICATION ENCRYPTED PASSWORD '$REPLICATION_PASSWORD';" || echo "Replication user already exists"
    
    # Force grant replication privilege (in case user was created without it, e.g. if same as app user)
    sudo -u postgres /usr/lib/postgresql/18/bin/psql -c "ALTER USER $REPLICATION_USER WITH REPLICATION;"
    
    # Update pg_hba.conf
    cat >> /etc/postgresql/18/main/pg_hba.conf << EOF

# Replication connections
host    replication     $REPLICATION_USER    127.0.0.1/32            md5
host    replication     $REPLICATION_USER    ::1/128                 md5
EOF
    
    # Update postgresql.conf
    cat >> /etc/postgresql/18/main/postgresql.conf << EOF

# Replication settings ($DB_REPLICAS replicas)
wal_level = replica
max_wal_senders = 10
wal_keep_size = 128
hot_standby = on
EOF
    
    # Restart primary
    systemctl restart postgresql
    
    echo -e "${GREEN}✓ Primary server configured for replication${NC}"
    
    # Create replicas
    for i in $(seq 1 $DB_REPLICAS); do
        STANDBY_PORT=$((5432 + i))
        DATA_DIR_STANDBY="/var/lib/postgresql/18/standby$i"
        
        echo -e "${YELLOW}   Creating replica $i (port $STANDBY_PORT)...${NC}"
        
        # Clean up previous data if exists (ensures re-run capability)
        if [ -d "$DATA_DIR_STANDBY" ]; then
            echo -e "${YELLOW}   Cleaning up existing directory $DATA_DIR_STANDBY...${NC}"
            rm -rf $DATA_DIR_STANDBY
        fi
        
        mkdir -p $DATA_DIR_STANDBY
        chown postgres:postgres $DATA_DIR_STANDBY
        chmod 700 $DATA_DIR_STANDBY
        
        # Create base backup (using env to pass password securely)
        sudo -u postgres env PGPASSWORD=$REPLICATION_PASSWORD pg_basebackup -h localhost -D $DATA_DIR_STANDBY -U $REPLICATION_USER -v -P -X stream
        
        # Ensure permissions remain correct after backup
        chmod 700 $DATA_DIR_STANDBY
        
        # Create standby.signal
        sudo -u postgres touch $DATA_DIR_STANDBY/standby.signal
        
        # Fix Configuration: Remove symlinks/files copied from primary to ensure isolation
        rm -f $DATA_DIR_STANDBY/postgresql.conf
        rm -f $DATA_DIR_STANDBY/pg_hba.conf
        rm -f $DATA_DIR_STANDBY/postgresql.auto.conf
        
        # Create log directory for standby
        mkdir -p /var/log/postgresql
        chown postgres:postgres /var/log/postgresql

        # Create isolated postgresql.conf for standby with logging
        cat > $DATA_DIR_STANDBY/postgresql.conf << EOF
data_directory = '$DATA_DIR_STANDBY'
hba_file = '$DATA_DIR_STANDBY/pg_hba.conf'
ident_file = '$DATA_DIR_STANDBY/pg_ident.conf'
port = $STANDBY_PORT
listen_addresses = '*'
max_connections = 100
shared_buffers = 128MB
dynamic_shared_memory_type = posix
hot_standby = on
primary_conninfo = 'host=localhost port=5432 user=$REPLICATION_USER password=$REPLICATION_PASSWORD'

# Logging
logging_collector = on
log_directory = '/var/log/postgresql'
log_filename = 'standby$i.log'
log_rotation_age = 1d
log_rotation_size = 10MB

# Locations
unix_socket_directories = '/var/run/postgresql'
EOF

        # Create empty postgresql.auto.conf to suppress warning
        touch $DATA_DIR_STANDBY/postgresql.auto.conf
        chown postgres:postgres $DATA_DIR_STANDBY/postgresql.auto.conf

        # Create isolated pg_hba.conf
        cat > $DATA_DIR_STANDBY/pg_hba.conf << EOF
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             all                                     peer
host    all             all             127.0.0.1/32            md5
host    all             all             ::1/128                 md5
host    replication     $REPLICATION_USER    127.0.0.1/32       md5
EOF
        
        chown postgres:postgres $DATA_DIR_STANDBY/postgresql.conf
        chown postgres:postgres $DATA_DIR_STANDBY/pg_hba.conf
        
        # Create systemd service
        cat > /etc/systemd/system/postgresql-standby$i.service << EOF
[Unit]
Description=PostgreSQL 18 Standby Server $i
After=network.target postgresql.service

[Service]
Type=forking
User=postgres
Group=postgres
# PIDFile is critical for systemd to track forking services correctly
PIDFile=$DATA_DIR_STANDBY/postmaster.pid
ExecStart=/usr/lib/postgresql/18/bin/pg_ctl start -D $DATA_DIR_STANDBY -l /var/log/postgresql/standby$i-startup.log -w -t 300
ExecStop=/usr/lib/postgresql/18/bin/pg_ctl stop -D $DATA_DIR_STANDBY -m fast
ExecReload=/usr/lib/postgresql/18/bin/pg_ctl reload -D $DATA_DIR_STANDBY
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
        
        systemctl daemon-reload
        systemctl enable postgresql-standby$i
        systemctl start postgresql-standby$i
        
        echo -e "${GREEN}   ✓ Replica $i created (port $STANDBY_PORT)${NC}"
    done
    
    echo -e "${GREEN}✓ All $DB_REPLICAS replicas configured${NC}"
fi

# Automated Backup Setup
if [ "$BACKUP_CHOICE" = "1" ]; then
    echo ""
    echo -e "${YELLOW}Step 7: Setting up automated backups...${NC}"
    
    # Create backup script
    cat > $APP_DIR/backup_postgres.sh << 'BACKUP_SCRIPT'
#!/bin/bash
# Automated PostgreSQL backup script

BACKUP_DIR="/opt/puxbay/backups/postgres"
DB_NAME="puxbay"
DB_USER="puxbay"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${DATE}.sql.gz"

mkdir -p $BACKUP_DIR

# Perform backup
sudo -u postgres pg_dump $DB_NAME | gzip > $BACKUP_FILE

if [ $? -eq 0 ]; then
    echo "✓ Backup completed: $BACKUP_FILE"
    # Delete old backups
    find $BACKUP_DIR -name "*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
    
    # Sync with Django Admin
    cd /opt/puxbay
    source venv/bin/activate
    python manage.py sync_backups
else
    echo "✗ Backup failed!"
    exit 1
fi
BACKUP_SCRIPT
    
    chmod +x $APP_DIR/backup_postgres.sh
    
    # Add to crontab (daily at 2 AM)
    (crontab -l 2>/dev/null; echo "0 2 * * * $APP_DIR/backup_postgres.sh >> $APP_DIR/logs/backup.log 2>&1") | crontab -
    
    echo -e "${GREEN}✓ Automated backups configured (daily at 2 AM)${NC}"
fi

echo ""
echo -e "${YELLOW}Step 8: Running migrations...${NC}"
python manage.py migrate --noinput

echo -e "${GREEN}✓ Migrations completed${NC}"

echo -e "${YELLOW}Step 9: Collecting static files...${NC}"
python manage.py collectstatic --noinput

echo -e "${GREEN}✓ Static files collected${NC}"

echo ""
echo "========================================="
echo "Phase 3: Application Replicas Setup"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 10: Setting up Supervisor with $APP_REPLICAS replicas...${NC}"

# Create Supervisor configuration
cat > /etc/supervisor/conf.d/$APP_NAME.conf << EOF
# Multiple Gunicorn instances (replicas)
EOF

# Generate replica configurations
REPLICA_PROGRAMS=""
for i in $(seq 1 $APP_REPLICAS); do
    REPLICA_NAME="${APP_NAME}_replica_${i}"
    if [ $i -eq 1 ]; then
        REPLICA_PROGRAMS="$REPLICA_NAME"
    else
        REPLICA_PROGRAMS="${REPLICA_PROGRAMS},$REPLICA_NAME"
    fi
    PORT=$((8000 + i))
    cat >> /etc/supervisor/conf.d/$APP_NAME.conf << EOF
[program:${REPLICA_NAME}]
command=$VENV_DIR/bin/daphne -b 127.0.0.1 -p $PORT --access-log - --proxy-headers possystem.asgi:application
directory=$APP_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$APP_DIR/logs/gunicorn-replica-${i}.log
environment=PATH="$VENV_DIR/bin"

EOF
done

# Add Celery workers
cat >> /etc/supervisor/conf.d/$APP_NAME.conf << EOF
[program:${APP_NAME}_celery]
command=$VENV_DIR/bin/celery -A possystem worker -l info --concurrency=4
directory=$APP_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$APP_DIR/logs/celery.log
environment=PATH="$VENV_DIR/bin"

[program:${APP_NAME}_celery_beat]
command=$VENV_DIR/bin/celery -A possystem beat -l info
directory=$APP_DIR
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=$APP_DIR/logs/celery-beat.log
environment=PATH="$VENV_DIR/bin"

# Group all replicas for easy management
[group:${APP_NAME}_replicas]
programs=$REPLICA_PROGRAMS
EOF

supervisorctl reread
supervisorctl update

echo -e "${GREEN}✓ Supervisor configured with $APP_REPLICAS replicas${NC}"

echo ""
echo "========================================="
echo "Phase 4: Nginx & SSL Configuration (Cloudflare)"
echo "========================================="
echo ""

# Generate upstream configuration
UPSTREAM_SERVERS=""
for i in $(seq 1 $APP_REPLICAS); do
    PORT=$((8000 + i))
    UPSTREAM_SERVERS="${UPSTREAM_SERVERS}    server 127.0.0.1:$PORT;\n"
done

echo -e "${YELLOW}Step 11: Configuring Nginx for Cloudflare...${NC}"

mkdir -p /etc/ssl/cloudflare
chmod 755 /etc/ssl/cloudflare

echo ""
echo "========================================="
echo "Cloudflare Origin Certificate Setup"
echo "========================================="
echo ""
echo "Please follow these steps in Cloudflare Dashboard:"
echo "1. Go to SSL/TLS → Origin Server"
echo "2. Click 'Create Certificate'"
echo "3. Hostnames: puxbay.com and *.puxbay.com"
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

# Create Nginx config for Cloudflare
cat > /etc/nginx/sites-available/$APP_NAME << EOF
upstream django_backend {
$(echo -e "$UPSTREAM_SERVERS")}

server {
    listen 443 ssl http2;
    server_name www.puxbay.com puxbay.com *.puxbay.com;

    ssl_certificate /etc/ssl/cloudflare/origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/origin-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;

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
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 131.0.72.0/22;
    real_ip_header CF-Connecting-IP;

    client_max_body_size 100M;

    location /static/ {
        alias /opt/puxbay/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/puxbay/media/;
        expires 7d;
    }

    location /ws/ {
        proxy_pass http://django_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    location / {
        proxy_pass http://django_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
        proxy_buffering off;
    }

    location /health/ {
        proxy_pass http://django_backend;
        access_log off;
    }
}

server {
    listen 443 ssl http2 default_server;
    server_name _;
    ssl_certificate /etc/ssl/cloudflare/origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/origin-key.pem;
    return 444;
}
EOF

ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo -e "${YELLOW}Testing Nginx configuration...${NC}"
nginx -t

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Nginx configuration is valid${NC}"
    systemctl restart nginx
    echo -e "${GREEN}✓ Nginx restarted${NC}"
else
    echo -e "${RED}✗ Nginx configuration has errors${NC}"
    exit 1
fi

echo ""
echo "========================================="
echo "Phase 5: Final Setup"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 12: Setting permissions...${NC}"
# Set general ownership
chown -R $USER:$GROUP $APP_DIR

# Set general permissions
chmod -R 755 $APP_DIR

# Media folder - needs write permissions for uploads
chown -R $USER:$GROUP $APP_DIR/media
chmod -R 775 $APP_DIR/media

# Static files folder - read-only for web server
chown -R $USER:$GROUP $APP_DIR/staticfiles
chmod -R 755 $APP_DIR/staticfiles

# Logs folder - needs write permissions
chmod -R 775 $APP_DIR/logs

# Backups folder - needs write permissions
chmod -R 775 $APP_DIR/backups

echo -e "${GREEN}✓ Permissions set${NC}"

echo -e "${YELLOW}Step 13: Starting services...${NC}"
supervisorctl start ${APP_NAME}_replicas:*
supervisorctl start ${APP_NAME}_celery
supervisorctl start ${APP_NAME}_celery_beat
systemctl enable redis-server
systemctl start redis-server
echo -e "${GREEN}✓ Services started${NC}"


echo ""
echo "========================================="
echo "Phase 6: Data Population"
echo "========================================="
echo ""

echo -e "${YELLOW}Step 14: Seeding initial data...${NC}"


# 2. Seed Features
echo "Running seed_features..."
python manage.py seed_features

# 3. Seed Billing (Plans & Gateways)
echo "Running seed_billing..."
python manage.py seed_billing

# 4. Setup Public Tenant
echo "Running setup_public_tenant..."
python manage.py setup_public_tenant

# 5. Populate Data (Initial Samples)
echo "Running populate_data..."
python manage.py populate_data

# 6. Seed Detailed Subscription Plans
echo "Running populate_plans..."
python manage.py populate_plans

# 7. Seed User Manual
echo "Running seed_manual..."
python manage.py seed_manual

# 8. Seed SEO Settings
echo "Running seed_seo..."
python manage.py seed_seo

echo -e "${GREEN}✓ Data population completed${NC}"

echo ""
echo "========================================="
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo "========================================="
echo ""
echo "Application: Puxbay"
echo "App Replicas: $APP_REPLICAS instances (ports 8001-$((8000 + APP_REPLICAS)))"

if [ "$REPLICATION_CHOICE" = "1" ]; then
    echo "DB Replicas: $DB_REPLICAS instances (ports 5433-$((5432 + DB_REPLICAS)))"
fi

if [ "$BACKUP_CHOICE" = "1" ]; then
    echo "Backups: Daily at 2 AM ($BACKUP_RETENTION_DAYS day retention)"
fi

echo ""
echo "SSL: Cloudflare Origin Certificate ✓"
echo ""
echo "📋 Cloudflare Dashboard Steps:"
echo "1. SSL/TLS → Set to 'Full (strict)'"
echo "2. DNS → Add A records (Proxied ☁️):"
echo "   @ → YOUR_SERVER_IP"
echo "   www → YOUR_SERVER_IP"
echo "   * → YOUR_SERVER_IP"
echo "3. SSL/TLS → Edge Certificates:"
echo "   ✓ Always Use HTTPS"
echo "   ✓ Automatic HTTPS Rewrites"

echo ""
echo "📋 Next Steps:"
echo "1. Update .env:"
echo "   ALLOWED_HOSTS=puxbay.com,www.puxbay.com,.puxbay.com
   REDIS_URL=redis://127.0.0.1:6379/1"

if [ "$REPLICATION_CHOICE" = "1" ]; then
    echo "   DB_REPLICA1_PORT=5433"
    echo "   DB_REPLICA2_PORT=5434"
    echo "   DB_REPLICA3_PORT=5435"
    echo "   DB_REPLICA4_PORT=5436"
    echo "   DB_REPLICA5_PORT=5437"
fi

echo ""
echo "2. Create superuser:"
echo "   cd $APP_DIR && source venv/bin/activate && python manage.py createsuperuser"
echo ""
echo "📊 Management Commands:"
echo "  - Status: sudo supervisorctl status"
echo "  - Restart: sudo supervisorctl restart ${APP_NAME}_replicas:*"
echo "  - Logs: tail -f $APP_DIR/logs/gunicorn-replica-1.log"

if [ "$REPLICATION_CHOICE" = "1" ]; then
    echo "  - DB Status: sudo -u postgres psql -c \"SELECT * FROM pg_stat_replication;\""
fi

if [ "$BACKUP_CHOICE" = "1" ]; then
    echo "  - Manual Backup: $APP_DIR/backup_postgres.sh"
    echo "  - View Backups: ls -lh $APP_DIR/backups/postgres/"
fi

echo ""
echo "🚀 Puxbay is production-ready!"
echo ""
