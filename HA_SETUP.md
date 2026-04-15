# K3s High Availability (HA) Setup Guide

This guide explains how to add additional master nodes to your existing K3s cluster without downtime.

## Overview

Your K3s cluster currently supports two deployment modes:

1. **Single Master** (Current): One master node + worker nodes
2. **High Availability**: Multiple master nodes (3, 5, or 7 recommended) + worker nodes

## Why Add More Masters?

- **High Availability**: Cluster continues operating if one master fails
- **Load Distribution**: API server requests distributed across masters
- **Zero Downtime Maintenance**: Update masters one at a time
- **Production Ready**: Meets production cluster requirements

## Prerequisites

✅ **What You Need:**
- Existing K3s cluster must be running healthy
- Additional Raspberry Pi(s) for new master nodes
- Static IP addresses configured for new masters
- Same network access as existing cluster nodes
- Odd number of total masters (3, 5, or 7 for proper quorum)

## Step-by-Step: Adding Master Nodes

### Step 1: Prepare New Raspberry Pi(s)

1. Flash Raspberry Pi OS on new Pi(s)
2. Configure static IP addresses (use `configure-static-ips.yml` playbook)
3. Ensure SSH access is working
4. Verify network connectivity to existing cluster

### Step 2: Update Inventory

Edit `ansible/inventory.yml` and add your new master nodes:

```yaml
additional_masters:
  hosts:
    pi-06:
      ansible_host: 10.10.10.50
      ansible_user: pi
      ansible_ssh_private_key_file: ~/.ssh/raspberrypi_rsa
    pi-07:
      ansible_host: 10.10.10.51
      ansible_user: pi
      ansible_ssh_private_key_file: ~/.ssh/raspberrypi_rsa
```

**Important**: For proper etcd quorum, use an **odd number** of total masters:
- 1 existing master + 2 additional = ✅ 3 total (recommended)
- 1 existing master + 4 additional = ✅ 5 total (better resilience)
- 1 existing master + 1 additional = ❌ 2 total (NOT recommended - no quorum on failure)

### Step 3: Run the Add Masters Playbook

```bash
cd ansible
ansible-playbook -i inventory.yml playbooks/add-masters.yml
```

The playbook will:
1. ✅ Verify primary master is healthy
2. ✅ Prepare new nodes (install prerequisites)
3. ✅ Retrieve cluster token from primary master
4. ✅ Install K3s in server mode on new nodes
5. ✅ Join new masters to the cluster
6. ✅ Verify all masters are Ready
7. ✅ Display cluster status and next steps

### Step 4: Verify HA Configuration

After the playbook completes, verify your HA setup:

```bash
# Check all nodes
kubectl get nodes -o wide

# Verify etcd members
kubectl get endpoints -n kube-system k3s -o yaml

# Check master node count
kubectl get nodes -l node-role.kubernetes.io/master=true
```

You should see all your master nodes listed and in "Ready" state.

## Load Balancer Setup (Recommended for Production)

For production HA, use a load balancer in front of your master nodes:

### Option 1: HAProxy on a Separate Host

Install HAProxy on a dedicated host (or virtual IP):

```bash
# /etc/haproxy/haproxy.cfg
frontend k3s-api
  bind *:6443
  mode tcp
  option tcplog
  default_backend k3s-masters

backend k3s-masters
  mode tcp
  balance roundrobin
  server pi-01 10.10.10.230:6443 check
  server pi-06 10.10.10.50:6443 check
  server pi-07 10.10.10.51:6443 check
```

### Option 2: Keepalived + HAProxy (Virtual IP)

Use Keepalived for a floating VIP that moves if the load balancer fails.

### Update Kubeconfig to Use Load Balancer

```bash
# Edit your kubeconfig
kubectl config set-cluster default --server=https://<LOAD_BALANCER_IP>:6443
```

## Testing HA Functionality

### Test 1: Master Node Failure

1. Stop K3s on one master:
   ```bash
   ssh pi@<master-node>
   sudo systemctl stop k3s
   ```

2. Verify cluster still works:
   ```bash
   kubectl get nodes
   kubectl get pods -A
   ```

3. Restart the master:
   ```bash
   sudo systemctl start k3s
   ```

### Test 2: API Server Load Distribution

Check which master is serving requests:
```bash
kubectl get --raw /version
```

## Monitoring HA Cluster

### Check etcd Cluster Health

```bash
# List etcd members
kubectl exec -n kube-system $(kubectl get pods -n kube-system -l component=etcd -o name | head -1) -- etcdctl member list

# Check etcd health
kubectl exec -n kube-system $(kubectl get pods -n kube-system -l component=etcd -o name | head -1) -- etcdctl endpoint health
```

### Monitor Master Nodes

```bash
# Check all master nodes
kubectl get nodes -l node-role.kubernetes.io/master=true

# Check system pods on masters
kubectl get pods -n kube-system -o wide | grep $(kubectl get nodes -l node-role.kubernetes.io/master=true -o name | sed 's/node\///')
```

## Common Issues and Troubleshooting

### Issue: New Master Not Joining

**Symptoms**: New master node doesn't appear in `kubectl get nodes`

**Solutions**:
1. Check K3s service status:
   ```bash
   ssh pi@<new-master>
   sudo systemctl status k3s
   sudo journalctl -u k3s -n 100
   ```

2. Verify network connectivity to primary master:
   ```bash
   curl -k https://<primary-master-ip>:6443
   ```

3. Check token is correct:
   ```bash
   # On primary master
   sudo cat /var/lib/rancher/k3s/server/node-token
   ```

### Issue: etcd Not Forming Quorum

**Symptoms**: Cluster API becomes unavailable, etcd errors in logs

**Solutions**:
1. Ensure odd number of masters (3, 5, or 7)
2. Check all masters are running:
   ```bash
   ansible master,additional_masters -i inventory.yml -m shell -a "systemctl status k3s" --become
   ```

3. Check etcd logs:
   ```bash
   kubectl logs -n kube-system -l component=etcd
   ```

### Issue: Workers Still Pointing to Single Master

**Symptoms**: Workers lose connection if primary master goes down

**Solutions**:
1. Reconfigure workers to use load balancer:
   ```bash
   # Edit /etc/systemd/system/k3s-agent.service.env on each worker
   K3S_URL=https://<LOAD_BALANCER_IP>:6443

   # Restart agent
   sudo systemctl restart k3s-agent
   ```

## Updating Worker Nodes to Use HA Masters

After adding masters, update workers to use load balancer (optional but recommended):

1. Set up load balancer (see above)

2. Update worker configuration:
   ```bash
   # On each worker node
   sudo sed -i 's|K3S_URL=.*|K3S_URL=https://<LOAD_BALANCER_IP>:6443|' \
     /etc/systemd/system/k3s-agent.service.env

   sudo systemctl daemon-reload
   sudo systemctl restart k3s-agent
   ```

## Rollback: Removing Additional Masters

If you need to remove additional masters:

```bash
# On the master to remove
ssh pi@<master-to-remove>
sudo /usr/local/bin/k3s-killall.sh
sudo /usr/local/bin/k3s-uninstall.sh

# On primary master, verify removal
kubectl get nodes
kubectl get endpoints -n kube-system k3s
```

## Architecture Diagrams

### Before (Single Master)
```
┌─────────────────┐
│   Master (1)    │
│   pi-01         │
└────────┬────────┘
         │
    ┌────┴─────┬─────────┬─────────┐
    │          │         │         │
┌───▼───┐ ┌───▼───┐ ┌──▼────┐ ┌──▼────┐
│Worker │ │Worker │ │Worker │ │Worker │
│ pi-02 │ │ pi-03 │ │ pi-04 │ │ pi-05 │
└───────┘ └───────┘ └───────┘ └───────┘
```

### After (HA with 3 Masters)
```
      ┌─────────────────┐
      │  Load Balancer  │  (Optional but recommended)
      │   (HAProxy)     │
      └────────┬────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐  ┌──▼────┐  ┌──▼────┐
│Master │  │Master │  │Master │
│ pi-01 │  │ pi-06 │  │ pi-07 │
└───┬───┘  └───┬───┘  └───┬───┘
    │          │          │
    └──────┬───┴───┬──────┘
           │       │
    ┌──────┴───┬───┴────┬─────────┐
    │          │        │         │
┌───▼───┐ ┌───▼───┐ ┌──▼────┐ ┌──▼────┐
│Worker │ │Worker │ │Worker │ │Worker │
│ pi-02 │ │ pi-03 │ │ pi-04 │ │ pi-05 │
└───────┘ └───────┘ └───────┘ └───────┘
```

## Best Practices

1. ✅ **Always use odd number of masters**: 3, 5, or 7 for proper etcd quorum
2. ✅ **Deploy load balancer**: Don't rely on a single master IP
3. ✅ **Monitor etcd health**: Check regularly with `etcdctl` commands
4. ✅ **Test failover**: Regularly test master node failures
5. ✅ **Backup etcd**: Regular backups of etcd data
6. ✅ **Keep versions in sync**: All masters should run same K3s version

## Resources

- [K3s High Availability Documentation](https://docs.k3s.io/datastore/ha)
- [K3s Embedded etcd](https://docs.k3s.io/datastore/ha-embedded)
- [etcd Best Practices](https://etcd.io/docs/v3.5/op-guide/)

## Questions?

If you encounter issues:
1. Check K3s logs: `sudo journalctl -u k3s -f`
2. Verify etcd health: `kubectl get endpoints -n kube-system k3s`
3. Check node status: `kubectl get nodes -o wide`
4. Review the playbook output for any errors
