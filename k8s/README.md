# Kubernetes Deployment Guide

This guide explains how to deploy the WebChatApp to a Kubernetes cluster with Cloudflare Tunnel for external access.

## Prerequisites

1. **Kubernetes Cluster**: A running K8s cluster (e.g., Ubuntu with k3s, microk8s, or kubeadm)
2. **kubectl**: Configured to connect to your cluster
3. **Docker Registry**: Access to a container registry (Docker Hub, GitHub Container Registry, etc.)
4. **Cloudflare Account**: With a domain configured

## Step 1: Build and Push Docker Images

First, build and push the Docker images to your container registry.

```bash
# Set your registry (replace with your actual registry)
export REGISTRY=your-dockerhub-username
# or for GitHub Container Registry:
# export REGISTRY=ghcr.io/your-username

# Build and push backend
cd backend
docker build -t $REGISTRY/webchatapp-backend:latest .
docker push $REGISTRY/webchatapp-backend:latest

# Build and push frontend
cd ../frontend
docker build -t $REGISTRY/webchatapp-frontend:latest .
docker push $REGISTRY/webchatapp-frontend:latest
```

## Step 2: Create Cloudflare Tunnel

1. Log into [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Go to **Networks** → **Tunnels**
3. Click **Create a tunnel**
4. Choose **Cloudflared** connector type
5. Name your tunnel (e.g., `webchatapp-tunnel`)
6. Copy the tunnel token (it looks like a long base64 string)

## Step 3: Configure Kubernetes Secrets

Edit `k8s/secrets.yaml` and replace the placeholder values:

```yaml
stringData:
  JWT_SECRET_KEY: "your-secure-jwt-secret-key-min-32-chars"
  JWT_REFRESH_SECRET_KEY: "your-secure-refresh-secret-key-min-32-chars"  
  ENCRYPTION_MASTER_KEY: "your-32-char-encryption-key!!"
  CLOUDFLARE_TUNNEL_TOKEN: "your-tunnel-token-from-cloudflare"
```

**Important**: Generate secure random keys for production:

```bash
# Generate random keys (run on Linux/Mac)
openssl rand -base64 32  # For JWT secrets
openssl rand -base64 24 | head -c 32  # For encryption key (must be exactly 32 chars)
```

## Step 4: Update Image References

Edit the deployment files to use your registry:

**k8s/backend-deployment.yaml:**
```yaml
image: your-registry/webchatapp-backend:latest
```

**k8s/frontend-deployment.yaml:**
```yaml
image: your-registry/webchatapp-frontend:latest
```

## Step 5: Configure Cloudflare Tunnel Public Hostname

In Cloudflare Zero Trust Dashboard → Networks → Tunnels → Your Tunnel → Public Hostname:

| Subdomain | Domain | Path | Service |
|-----------|--------|------|---------|
| chat | yourdomain.com | /api/* | http://backend-service:5000 |
| chat | yourdomain.com | /socket.io/* | http://backend-service:5000 |
| chat | yourdomain.com | /* | http://frontend-service:3000 |

## Step 6: Deploy to Kubernetes

```bash
# Make deploy script executable
chmod +x k8s/deploy.sh

# Run deployment
cd k8s
./deploy.sh
```

Or deploy manually:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/storage.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/cloudflared-deployment.yaml

# Check status
kubectl -n webchatapp get pods
kubectl -n webchatapp get services
```

## Verification

1. Check all pods are running:
   ```bash
   kubectl -n webchatapp get pods
   ```

2. Check logs:
   ```bash
   kubectl -n webchatapp logs -l app=backend
   kubectl -n webchatapp logs -l app=frontend
   kubectl -n webchatapp logs -l app=cloudflared
   ```

3. Visit your domain: `https://chat.yourdomain.com`

## Troubleshooting

### Pods not starting
```bash
kubectl -n webchatapp describe pod <pod-name>
kubectl -n webchatapp logs <pod-name>
```

### Image pull errors
```bash
kubectl create secret docker-registry regcred \
  --docker-server=<your-registry> \
  --docker-username=<your-username> \
  --docker-password=<your-password> \
  -n webchatapp
```

Then add `imagePullSecrets` to deployments.

### Cloudflare Tunnel not connecting
```bash
kubectl -n webchatapp logs -l app=cloudflared
```

## Security Notes

1. Never commit real secrets to version control
2. Use Kubernetes Secrets or external secret management
3. Enable Cloudflare Access for additional authentication
