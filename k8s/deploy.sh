#!/bin/bash

# WebChatApp Kubernetes Deployment Script
set -e

echo "=== Deploying WebChatApp to Kubernetes ==="

# Create namespace
echo "Creating namespace..."
kubectl apply -f namespace.yaml

# Create config and secrets
echo "Creating ConfigMap and Secrets..."
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml

# Create persistent storage
echo "Creating Persistent Volume Claims..."
kubectl apply -f storage.yaml

# Deploy backend
echo "Deploying Backend..."
kubectl apply -f backend-deployment.yaml

# Deploy frontend
echo "Deploying Frontend..."
kubectl apply -f frontend-deployment.yaml

# Deploy Cloudflare Tunnel
echo "Deploying Cloudflare Tunnel..."
kubectl apply -f cloudflared-deployment.yaml

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Checking pod status..."
kubectl -n webchatapp get pods

echo ""
echo "Checking services..."
kubectl -n webchatapp get services

echo ""
echo "=== Next Steps ==="
echo "1. Update secrets.yaml with your actual keys"
echo "2. Update deployment images with your registry"
echo "3. Configure Cloudflare Tunnel public hostname in dashboard"
echo "4. Access your app via your Cloudflare domain"
