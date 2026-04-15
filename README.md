# Raspberry Pi K3s Cluster - Ansible

Enterprise-grade Ansible automation for deploying K3s Kubernetes clusters on Raspberry Pi.

## Overview

This project deploys a production-ready K3s Kubernetes cluster on Raspberry Pi 4B devices with:
- 1 Master Node (control plane) - **Can be scaled to 3, 5, or 7 for HA**
- 4 Worker Nodes (easily scalable)
- Automatic prerequisite configuration
- Zero-downtime HA expansion support
- Embedded etcd for multi-master clusters

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Raspberry Pi K3s Cluster                       │
├─────────────────────────────────────────────────┤
│                                                 │
│  pi-01 (10.10.10.230) - Master Node             │
│  ├─ K3s Server                                  │
│  ├─ etcd (embedded)                             │
│  ├─ API Server, Scheduler, Controller           │
│  └─ No workload pods (tainted)                  │
│                                                 │
│  pi-02 (10.10.10.25) - Worker Node 1            │
│  ├─ K3s Agent                                   │
│  └─ Workload pods                               │
│                                                 │
│  pi-03 (10.10.10.45) - Worker Node 2            │
│  ├─ K3s Agent                                   │
│  └─ Workload pods                               │
│                                                 │
│  pi-04 (10.10.10.148) - Worker Node 3           │
│  ├─ K3s Agent                                   │
│  └─ Workload pods                               │
│                                                 │
│  pi-05 (10.10.10.216) - Worker Node 4           │
│  ├─ K3s Agent                                   │
│  └─ Workload pods                               │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Directory Structure

```
ansible/
├── inventory.yml              # Cluster node inventory
├── group_vars/
│   └── all.yml               # K3s configuration variables
├── playbooks/                # All playbooks
│   ├── k3s-install.yml      # Main cluster installation
│   └── k3s-reset.yml        # Complete cluster removal
├── tasks/                    # Reusable task files
│   ├── prerequisites.yml    # System preparation
│   ├── master-setup.yml     # Master node setup
│   └── worker-setup.yml     # Worker node setup
└── templates/                # Jinja2 templates (future use)
```

## Prerequisites

### Raspberry Pi Requirements
- Raspberry Pi 4B (4GB+ RAM recommended)
- Raspberry Pi OS Lite (64-bit) installed via network boot
- All nodes accessible via SSH
- SSH key authentication configured

### Control Machine Requirements
- Docker (for running Ansible in container)
- OR native Ansible 2.14+ installation

## Quick Start

### 1. Configure Static IP Addresses (REQUIRED for Production)

**Important:** Before installing K3s, configure static IPs to prevent IP changes on reboot.

First, update `inventory.yml` with your current Pi IP addresses (from DHCP):

```yaml
master:
  hosts:
    pi-01:
      ansible_host: 10.10.10.230  # Your master IP

workers:
  hosts:
    pi-02:
      ansible_host: 10.10.10.25   # Your worker IPs
    pi-03:
      ansible_host: 10.10.10.45
    pi-04:
      ansible_host: 10.10.10.148
    pi-05:
      ansible_host: 10.10.10.216
```

Then run the static IP configuration playbook:

```bash
ansible-playbook -i inventory.yml playbooks/configure-static-ips.yml
```

This will:
- Configure static IPs on all Raspberry Pis using their current addresses
- Ensure IPs persist across reboots
- Prevent DHCP from changing IPs during K3s installation

**Optional:** Customize DNS servers in `group_vars/all.yml`:
```yaml
dns_servers: "8.8.8.8 8.8.4.4"  # Change to your preferred DNS
```

### 2. Configure Cluster Settings

Edit `group_vars/all.yml` to customize:
- K3s version
- Network CIDRs
- Feature flags
- Resource limits

### 3. Install Cluster

**From Docker (Windows/macOS):**

```bash
cd ansible/

docker run --rm \
  -v "c:/Users/Spencer/.ssh/raspberrypi_rsa:/tmp/key:ro" \
  -v "$(pwd)/..:/workspace:ro" \
  cytopia/ansible:latest-tools sh -c '\
    mkdir -p /root/.ssh && \
    cp /tmp/key /root/.ssh/raspberrypi_rsa && \
    chmod 600 /root/.ssh/raspberrypi_rsa && \
    cd /workspace/ansible && \
    ansible-playbook -i inventory.yml playbooks/k3s-install.yml \
    --ssh-common-args="-o StrictHostKeyChecking=no"'
```

**From Linux/Native Ansible:**

```bash
cd ansible/
ansible-playbook -i inventory.yml playbooks/k3s-install.yml
```

### 4. Access Your Cluster

**Option 1: Use Local Kubeconfig (Recommended)**

After installation completes, the kubeconfig is automatically downloaded to `rpi-k3s/kubeconfig`:

```bash
# Set KUBECONFIG environment variable (from project root)
export KUBECONFIG=$(pwd)/kubeconfig

# Or use absolute path
export KUBECONFIG=/path/to/rpi-k3s/kubeconfig

# Check cluster status from your local machine
kubectl get nodes
kubectl get pods -A
kubectl cluster-info
```

**Option 2: SSH to Master Node**

```bash
ssh pi@10.10.10.230
kubectl get nodes
kubectl get pods -A
```

## Configuration Options

### K3s Version

Edit `group_vars/all.yml`:

```yaml
k3s_version: v1.29.10+k3s1  # Change to desired version
```

### Disable Default Components

By default, Traefik and ServiceLB are disabled. To enable them:

```yaml
k3s_master_args:
  # - "--disable=traefik"      # Comment out to enable
  # - "--disable=servicelb"    # Comment out to enable
```

### Network Configuration

```yaml
k3s_cluster_cidr: "10.42.0.0/16"  # Pod network
k3s_service_cidr: "10.43.0.0/16"  # Service network
k3s_flannel_backend: vxlan         # or wireguard
```

### Install Optional Tools

```yaml
install_helm: true          # Helm package manager
install_k9s: true          # Terminal UI for K8s
install_kubectl_completion: true
```

## Available Playbooks

### add-masters.yml

Adds additional master nodes to an existing K3s cluster for high availability without downtime.

**Usage:**
```bash
ansible-playbook -i inventory.yml playbooks/add-masters.yml
```

**What it does:**
1. Verifies primary master is healthy
2. Prepares new master nodes (prerequisites)
3. Retrieves cluster token from primary master
4. Installs K3s in server mode on new nodes
5. Joins new masters to existing cluster using embedded etcd
6. Verifies cluster HA configuration

**Prerequisites:**
- Existing K3s cluster must be running
- New master nodes added to `additional_masters` group in inventory.yml
- Odd number of total masters recommended (3, 5, or 7)

**See [../HA_SETUP.md](../HA_SETUP.md) for complete HA setup guide**

### configure-static-ips.yml

Configures static IP addresses on all Raspberry Pi nodes for production stability.

**Usage:**
```bash
ansible-playbook -i inventory.yml playbooks/configure-static-ips.yml
```

**What it does:**
1. Reads current IP from inventory.yml for each node
2. Configures static IP in /etc/dhcpcd.conf
3. Backs up existing configuration
4. Restarts network service
5. Verifies all nodes are still accessible

**Important:**
- Run this BEFORE k3s-install.yml
- Prevents IP changes during K3s installation reboots
- Required for production clusters

### k3s-install.yml

Main installation playbook that:
1. Configures system prerequisites (cgroups, kernel modules, iptables)
2. Installs K3s server on master node
3. Installs K3s agents on worker nodes
4. Verifies cluster health

**Usage:**
```bash
ansible-playbook -i inventory.yml playbooks/k3s-install.yml
```

**Tags:**
- `prereqs` - Only run prerequisites
- `master` - Only setup master
- `worker` - Only setup workers
- `verify` - Only verification

**Examples:**
```bash
# Only prepare systems (no K3s install)
ansible-playbook -i inventory.yml playbooks/k3s-install.yml --tags prereqs

# Only setup master node
ansible-playbook -i inventory.yml playbooks/k3s-install.yml --tags master

# Skip verification
ansible-playbook -i inventory.yml playbooks/k3s-install.yml --skip-tags verify
```

### k3s-reset.yml

Complete cluster removal playbook that:
1. Uninstalls K3s from all workers
2. Uninstalls K3s from master
3. Removes all K3s files and configurations
4. Cleans up processes and network config

**Usage:**
```bash
ansible-playbook -i inventory.yml playbooks/k3s-reset.yml
```

**Note:** Preserves prerequisites (cgroups, iptables). Reboot recommended after reset.

## Common Tasks

### Check Cluster Status

```bash
ssh pi@10.10.10.230
kubectl get nodes -o wide
kubectl get pods -A
kubectl cluster-info
```

### Deploy Test Application

```bash
# Create nginx deployment
kubectl create deployment nginx --image=nginx --replicas=3

# Expose as service
kubectl expose deployment nginx --port=80 --type=NodePort

# Get service details
kubectl get svc nginx

# Access via any node IP:PORT
```

### View Logs

```bash
# Master node logs
sudo journalctl -u k3s -f

# Worker node logs
sudo journalctl -u k3s-agent -f
```

### Upgrade Cluster

1. Update version in `group_vars/all.yml`:
   ```yaml
   k3s_version: v1.30.0+k3s1
   ```

2. Rerun installation:
   ```bash
   ansible-playbook -i inventory.yml playbooks/k3s-install.yml
   ```

### Add Worker Node

1. Add to `inventory.yml`:
   ```yaml
   workers:
     hosts:
       pi-06:
         ansible_host: 10.10.10.219
   ```

2. Run playbook:
   ```bash
   ansible-playbook -i inventory.yml playbooks/k3s-install.yml --limit pi-06
   ```

### Add Master Nodes for High Availability

To add additional master nodes for HA without downtime:

1. Add new masters to `inventory.yml`:
   ```yaml
   additional_masters:
     hosts:
       pi-06:
         ansible_host: 10.10.10.50
       pi-07:
         ansible_host: 10.10.10.51
   ```

2. Run the add-masters playbook:
   ```bash
   ansible-playbook -i inventory.yml playbooks/add-masters.yml
   ```

**For detailed HA setup instructions, see [../HA_SETUP.md](../HA_SETUP.md)**

Important:
- Use an odd number of total masters (3, 5, or 7) for proper etcd quorum
- Set up a load balancer for production HA
- This can be done without taking down your existing cluster

### Remove Worker Node

```bash
# On master node
kubectl drain pi-06 --ignore-daemonsets --delete-emptydir-data
kubectl delete node pi-06

# On worker node
sudo /usr/local/bin/k3s-agent-uninstall.sh
```

## Troubleshooting

### Nodes Not Ready

```bash
# Check node status
kubectl describe node pi-02

# Check kubelet logs
sudo journalctl -u k3s-agent -f
```

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod <pod-name>

# Check events
kubectl get events --sort-by='.lastTimestamp'
```

### Network Issues

```bash
# Check flannel
kubectl get pods -n kube-system | grep flannel

# Check CNI plugins
ls -la /opt/cni/bin/
```

### Reset and Reinstall

```bash
# Complete reset
ansible-playbook -i inventory.yml playbooks/k3s-reset.yml

# Reboot all nodes
ansible k3s_cluster -i inventory.yml -m reboot --become

# Reinstall
ansible-playbook -i inventory.yml playbooks/k3s-install.yml
```

## Performance Tips

### Raspberry Pi Optimizations

1. **Use SSD over SD Card** - Dramatically improves performance
2. **Overclock cautiously** - Can improve CPU performance but monitor temps
3. **Adequate cooling** - Keep temps under 70°C under load
4. **Power supply** - Use official 3A+ power supplies
5. **Network** - Use gigabit ethernet, not WiFi

### K3s Optimizations

```yaml
# In group_vars/all.yml

# Reduce resource usage
k3s_master_args:
  - "--disable=traefik"
  - "--disable=metrics-server"  # If not needed
  - "--kube-apiserver-arg=max-requests-inflight=400"
```

### Resource Limits

Set appropriate limits for workloads:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: nginx
spec:
  containers:
  - name: nginx
    image: nginx
    resources:
      limits:
        memory: "128Mi"
        cpu: "500m"
      requests:
        memory: "64Mi"
        cpu: "250m"
```

## Security Considerations

### Network Security

- K3s uses TLS for all internal communication
- Default ports: 6443 (API), 10250 (kubelet)
- Consider firewall rules for production

### Secrets Management

- Use Kubernetes secrets (base64 encoded)
- Consider sealed-secrets for GitOps
- Or external secret managers (Vault, AWS Secrets Manager)

### RBAC

- K3s includes RBAC by default
- Create service accounts with minimal permissions
- Avoid using default service account

### Updates

- Monitor K3s security advisories
- Update regularly using upgrade playbook
- Test upgrades in dev environment first

## Next Steps

After successful cluster deployment:

1. **Install Ingress Controller** (nginx-ingress, traefik)
2. **Setup Storage** (NFS, Longhorn, local-path)
3. **Install Monitoring** (Prometheus, Grafana)
4. **Setup GitOps** (ArgoCD, Flux)
5. **Deploy Applications** (Helm charts, manifests)

## Resources

- [K3s Documentation](https://docs.k3s.io/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Helm Charts](https://artifacthub.io/)
- [K3s GitHub](https://github.com/k3s-io/k3s)

## Support

For issues specific to this Ansible automation:
- Check logs: `sudo journalctl -u k3s -f`
- Verify prerequisites are met
- Ensure all nodes are reachable
- Try reset and reinstall

For K3s-specific issues:
- [K3s GitHub Issues](https://github.com/k3s-io/k3s/issues)
- [Rancher Slack](https://slack.rancher.io/)
