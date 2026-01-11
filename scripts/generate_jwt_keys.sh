#!/bin/bash
# Generate RSA key pair for JWT signing

echo "Generating JWT private key..."
openssl genrsa -out jwt_private.pem 2048

echo "Generating JWT public key..."
openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem

echo "Keys generated successfully!"
echo "Private key: jwt_private.pem"
echo "Public key: jwt_public.pem"
echo ""
echo "WARNING: Keep these keys secure and never commit them to version control!"

