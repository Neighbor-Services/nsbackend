#!/bin/bash
# Neighbor Service Staging Restart Script
# Centralized script to restart all staging application components.
# Usage: sudo bash restart_services_staging.sh

set -e

# Configuration
APP_NAME="ns_backend_staging"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================="
echo "Restarting ns_backend_staging Services"
echo "========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

echo -e "${YELLOW}1. Restarting Redis Instances...${NC}"
# Primary Redis
systemctl restart redis-server || echo "Primary Redis not found"
echo -e "${GREEN}✓ Redis services restarted${NC}"

echo -e "${YELLOW}2. Restarting Application (Supervisor)...${NC}"
supervisorctl restart ${APP_NAME}_app
echo -e "${GREEN}✓ Application restarted${NC}"

echo -e "${YELLOW}3. Restarting Celery Services...${NC}"
supervisorctl restart ${APP_NAME}_celery
supervisorctl restart ${APP_NAME}_celery_beat
echo -e "${GREEN}✓ Celery services restarted${NC}"

echo -e "${YELLOW}4. Restarting Nginx...${NC}"
systemctl restart nginx
echo -e "${GREEN}✓ Nginx restarted${NC}"

echo ""
echo "========================================="
echo -e "${GREEN}🎉 All staging services restarted successfully!${NC}"
echo "========================================="
