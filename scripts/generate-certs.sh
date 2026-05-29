#!/bin/bash
set -e

CERT_DIR="$(dirname "$0")/../nginx/certs"
mkdir -p "$CERT_DIR"

echo "Generating self-signed TLS certificates for development..."

# Generate CA key and certificate
openssl genrsa -out "$CERT_DIR/ca.key" 4096
openssl req -new -x509 -days 365 -key "$CERT_DIR/ca.key" \
    -out "$CERT_DIR/ca.crt" \
    -subj "/C=US/ST=Dev/L=Local/O=EDMS/CN=EDMS CA"

# Generate server key
openssl genrsa -out "$CERT_DIR/server.key" 2048

# Generate CSR with SANs
openssl req -new -key "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.csr" \
    -subj "/C=US/ST=Dev/L=Local/O=EDMS/CN=localhost"

# Create SAN config
cat > "$CERT_DIR/san.cnf" << EOF
[req]
distinguished_name = req_distinguished_name
[req_distinguished_name]
[v3_req]
subjectAltName = @alt_names
[alt_names]
DNS.1 = localhost
DNS.2 = *.edms.local
DNS.3 = edms.local
IP.1 = 127.0.0.1
EOF

# Sign server cert with CA
openssl x509 -req -days 365 \
    -in "$CERT_DIR/server.csr" \
    -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" -CAcreateserial \
    -out "$CERT_DIR/server.crt" \
    -extensions v3_req -extfile "$CERT_DIR/san.cnf"

# Clean up intermediate files
rm -f "$CERT_DIR/server.csr" "$CERT_DIR/san.cnf" "$CERT_DIR/ca.srl"

echo "Certificates generated in $CERT_DIR/"
echo "  - server.crt (server certificate)"
echo "  - server.key (server private key)"
echo "  - ca.crt (CA certificate for trust)"
echo "  - ca.key (CA private key)"
