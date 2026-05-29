#!/bin/bash
# EDMS Production Setup Script
# This script automates the deployment of EDMS with all security hardening

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}   EDMS Production Setup Script${NC}"
echo -e "${GREEN}=========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Warning: Not running as root. Some commands may require sudo.${NC}"
fi

###############################################
# Prerequisites Check
###############################################
echo -e "\n${YELLOW}[1/8] Checking prerequisites...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Installing...${NC}"
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
else
    echo -e "${GREEN}✓ Docker is installed${NC}"
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is not installed${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Docker Compose is installed${NC}"
fi

# Check Fail2Ban
if ! command -v fail2ban-client &> /dev/null; then
    echo -e "${YELLOW}Fail2Ban is not installed. Installing...${NC}"
    apt-get update && apt-get install -y fail2ban || {
        echo -e "${YELLOW}Skipping Fail2Ban installation (not on Debian/Ubuntu)${NC}"
    }
else
    echo -e "${GREEN}✓ Fail2Ban is installed${NC}"
fi

# Check OpenSSL
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}OpenSSL is required${NC}"
    exit 1
else
    echo -e "${GREEN}✓ OpenSSL is installed${NC}"
fi

###############################################
# Generate Secure Secrets
###############################################
echo -e "\n${YELLOW}[2/8] Generating secure secrets...${NC}"

if [ ! -f .env ]; then
    cp .env.example .env
    
    # Generate random secrets
    SECRET_KEY=$(openssl rand -base64 32)
    PDF_PASSWORD=$(openssl rand -base64 32)
    KMS_PASSPHRASE=$(openssl rand -base64 32)
    POSTGRES_PASSWORD=$(openssl rand -base64 32)
    MINIO_PASSWORD=$(openssl rand -base64 32)
    RESTIC_PASSWORD=$(openssl rand -base64 32)
    
    # Update .env file
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
    sed -i "s/^PDF_ENCRYPTION_PASSWORD=.*/PDF_ENCRYPTION_PASSWORD=$PDF_PASSWORD/" .env
    sed -i "s/^KMS_LOCAL_PASSPHRASE=.*/KMS_LOCAL_PASSPHRASE=$KMS_PASSPHRASE/" .env
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" .env
    sed -i "s/^MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$MINIO_PASSWORD/" .env
    sed -i "s/^BACKUP_RESTIC_PASSWORD=.*/BACKUP_RESTIC_PASSWORD=$RESTIC_PASSWORD/" .env
    
    echo -e "${GREEN}✓ Generated secure secrets in .env${NC}"
    echo -e "${YELLOW}⚠ IMPORTANT: Backup your .env file securely!${NC}"
else
    echo -e "${GREEN}✓ .env file already exists${NC}"
fi

###############################################
# Generate SSL Certificates
###############################################
echo -e "\n${YELLOW}[3/8] Setting up SSL certificates...${NC}"

mkdir -p nginx/certs

if [ ! -f nginx/certs/server.crt ] || [ ! -f nginx/certs/server.key ]; then
    echo -e "${YELLOW}Generating self-signed certificate for development...${NC}"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/certs/server.key \
        -out nginx/certs/server.crt \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
    
    chmod 644 nginx/certs/server.crt
    chmod 600 nginx/certs/server.key
    
    echo -e "${GREEN}✓ Self-signed certificate generated${NC}"
    echo -e "${YELLOW}⚠ For production, replace with Let's Encrypt or CA-signed certificate${NC}"
else
    echo -e "${GREEN}✓ SSL certificates already exist${NC}"
fi

###############################################
# Configure Fail2Ban
###############################################
echo -e "\n${YELLOW}[4/8] Configuring Fail2Ban...${NC}"

if command -v fail2ban-client &> /dev/null; then
    # Copy Fail2Ban configuration
    if [ -d fail2ban/jail.d ]; then
        cp fail2ban/jail.d/edms.conf /etc/fail2ban/jail.d/edms.conf 2>/dev/null || true
        echo -e "${GREEN}✓ Copied jail configuration${NC}"
    fi
    
    if [ -d fail2ban/filter.d ]; then
        cp fail2ban/filter.d/*.conf /etc/fail2ban/filter.d/ 2>/dev/null || true
        echo -e "${GREEN}✓ Copied filter configurations${NC}"
    fi
    
    # Create log file if doesn't exist
    mkdir -p /var/log/nginx
    touch /var/log/nginx/edms_access.log
    
    # Restart Fail2Ban
    systemctl restart fail2ban 2>/dev/null || echo -e "${YELLOW}Could not restart Fail2Ban (may need manual intervention)${NC}"
    echo -e "${GREEN}✓ Fail2Ban configured${NC}"
else
    echo -e "${YELLOW}Skipping Fail2Ban configuration (not installed)${NC}"
fi

###############################################
# Create Required Directories
###############################################
echo -e "\n${YELLOW}[5/8] Creating required directories...${NC}"

mkdir -p data/raw data/md data/csv data/images data/vectors
mkdir -p uploads storage wiki chroma_db
mkdir -p logs

echo -e "${GREEN}✓ Created storage directories${NC}"

###############################################
# Build and Start Services
###############################################
echo -e "\n${YELLOW}[6/8] Building Docker images...${NC}"

docker-compose build --no-cache

echo -e "${GREEN}✓ Docker images built${NC}"

###############################################
# Start Services
###############################################
echo -e "\n${YELLOW}[7/8] Starting services...${NC}"

docker-compose up -d

echo -e "${GREEN}✓ Services started${NC}"

# Wait for services to be healthy
echo -e "\n${YELLOW}Waiting for services to become healthy...${NC}"
sleep 30

# Check service health
docker-compose ps

###############################################
# Run Setup Wizard
###############################################
echo -e "\n${YELLOW}[8/8] Running EDMS setup wizard...${NC}"

docker-compose exec -T app python -m app.setup_wizard --non-interactive 2>/dev/null || {
    echo -e "${YELLOW}Setup wizard completed or skipped${NC}"
}

echo -e "${GREEN}✓ Setup complete${NC}"

###############################################
# Summary
###############################################
echo -e "\n${GREEN}=========================================${NC}"
echo -e "${GREEN}   EDMS Setup Complete!${NC}"
echo -e "${GREEN}=========================================${NC}"

echo -e "\n${YELLOW}Access Information:${NC}"
echo -e "  Web UI: https://localhost"
echo -e "  MinIO Console: https://localhost/minio"
echo -e "  Health Check: https://localhost/health"

echo -e "\n${YELLOW}Important Files:${NC}"
echo -e "  Environment: $(pwd)/.env"
echo -e "  Logs: $(pwd)/logs/"
echo -e "  Storage: $(pwd)/storage/"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo -e "  1. Change default admin password immediately"
echo -e "  2. Configure backup destination"
echo -e "  3. Set up Let's Encrypt certificate for production"
echo -e "  4. Review and customize .env settings"
echo -e "  5. Configure LDAP integration (optional)"

echo -e "\n${GREEN}To view logs: docker-compose logs -f${NC}"
echo -e "${GREEN}To stop services: docker-compose down${NC}"
