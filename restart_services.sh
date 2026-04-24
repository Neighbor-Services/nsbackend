#!/bin/bash
# Puxbay Service Restart Script
# Centralized script to restart all application components, including multiples Redis instances.
# Usage: sudo bash restart_services.sh

set -e

# Configuration
APP_NAME="ns_backend"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Restarting ns_backend Services"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

echo -e "${YELLOW}1. Restarting Redis Instances...${NC}"
# Primary Redis
systemctl restart redis-server || echo "Primary Redis not found"

# Secondary Redis Instances (redis2, redis3, etc.)
for service in $(systemctl list-units --type=service --state=active | grep -oE "redis[0-9]+" | sort -u); do
    echo "   Restarting ${service}..."
    systemctl restart ${service}
done
echo -e "${GREEN}✓ Redis services restarted${NC}"

echo -e "${YELLOW}2. Restarting Application Replicas (Supervisor)...${NC}"
supervisorctl restart ${APP_NAME}_replicas:*
echo -e "${GREEN}✓ Application replicas restarted${NC}"

echo -e "${YELLOW}3. Restarting Celery Services...${NC}"
supervisorctl restart ${APP_NAME}_celery
supervisorctl restart ${APP_NAME}_celery_beat
echo -e "${GREEN}✓ Celery services restarted${NC}"

echo -e "${YELLOW}4. Restarting Nginx...${NC}"
systemctl restart nginx
echo -e "${GREEN}✓ Nginx restarted${NC}"

echo ""
echo "========================================="
echo -e "${GREEN}🎉 All services restarted successfully!${NC}"
echo "========================================="
