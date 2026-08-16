# Cluster Configuration Guide

This directory supports multiple K3s cluster configurations. Choose the one that matches your setup.

## Available Clusters

### Single-Node RPi5 (Development/Testing)
- **Inventory:** `inventories/single-pi.yml`
- **Configuration:** `group_vars/single-pi/all.yml`
- **Usage:** Single Raspberry Pi 5 for development and testing
- **HA Enabled:** No

**Install:**
```bash
ansible-playbook -i inventories/single-pi.yml playbooks/k3s-install.yml
```

### Multi-Node Production (4 Workers + 1 Master)
- **Inventory:** `inventories/multinode.yml`
- **Configuration:** `group_vars/multinode/all.yml`
- **Usage:** Production workloads across 5 Raspberry Pis
- **HA Enabled:** Yes (can expand to 3, 5, 7 masters)

**Install:**
```bash
ansible-playbook -i inventories/multinode.yml playbooks/k3s-install.yml
```

## Directory Structure

```
ansible/
├── inventories/                  # Cluster inventories
│   ├── single-pi.yml            # Single-node RPi5
│   └── multinode.yml            # Multi-node production
├── group_vars/
│   ├── all.yml                  # Shared defaults
│   ├── single-pi/all.yml        # Single-pi cluster config
│   └── multinode/all.yml        # Multi-node cluster config
├── playbooks/                    # Ansible playbooks
├── tasks/                        # Reusable task files
└── CLUSTER-SETUP.md             # This file
```

## Configuration Priority

Ansible loads variables in this order (later overrides earlier):
1. `group_vars/all.yml` (defaults)
2. `group_vars/<cluster-type>/all.yml` (cluster-specific)
3. `inventories/<cluster-type>.yml` (host-specific)

## Customizing a Cluster

### 1. Update Node IPs/Hostnames
Edit the appropriate inventory file:
```yaml
# inventories/multinode.yml
workers:
  hosts:
    pi-02:
      ansible_host: 10.10.10.216  # Change to your IP
```

### 2. Change K3s Version
Edit the cluster config:
```yaml
# group_vars/multinode/all.yml
k3s_version: v1.30.0+k3s1
```

### 3. Add/Remove Features
Edit `group_vars/<cluster-type>/all.yml`:
```yaml
install_helm: true
install_k9s: true
```

## Common Operations

### Diagnose or Rejoin an Unhealthy Worker

Use `diagnose-and-rejoin-node.yml` for one worker at a time. It is read-only
unless a recovery mode and its matching confirmation string are supplied.

The target must exist in the selected inventory. For a node that has already
fallen out of the inventory, add it temporarily under `workers` with its
current IP and, when its Linux hostname differs from the Kubernetes node name,
set `k3s_node_name_override` for that host. Do not commit a temporary dead-node
entry just to perform recovery.

Run the read-only diagnosis first:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/diagnose-and-rejoin-node.yml \
  --limit pi-recovery \
  -e recovery_mode=diagnose
```

If the agent is installed but only needs a service restart:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/diagnose-and-rejoin-node.yml \
  --limit pi-recovery \
  -e recovery_mode=restart \
  -e confirm_restart=RESTART_K3S_AGENT
```

For a full worker rejoin, the playbook stops and uninstalls the existing
agent, then installs it again using a fresh token read from the primary
master:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/diagnose-and-rejoin-node.yml \
  --limit pi-recovery \
  -e recovery_mode=rejoin \
  -e confirm_rejoin=REJOIN_K3S_WORKER
```

The rejoin refuses to remove a node-local storage tree by default. If the
node has local-path PVC data, back it up or migrate it first. Only then may
the destructive cleanup be acknowledged explicitly:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/diagnose-and-rejoin-node.yml \
  --limit pi-recovery \
  -e recovery_mode=rejoin \
  -e confirm_rejoin=REJOIN_K3S_WORKER \
  -e allow_local_storage_reset=true
```

Deleting the stale Kubernetes node object is separate and requires a second
confirmation:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/diagnose-and-rejoin-node.yml \
  --limit pi-recovery \
  -e recovery_mode=rejoin \
  -e confirm_rejoin=REJOIN_K3S_WORKER \
  -e remove_stale_node=true \
  -e confirm_node_removal=DELETE_K3S_NODE
```

Do not use the rejoin mode on a control-plane node. It intentionally refuses
master targets; control-plane recovery needs a quorum-aware procedure.

### Configure Static IPs
```bash
# Single-pi cluster
ansible-playbook -i inventories/single-pi.yml playbooks/configure-static-ips.yml

# Multi-node cluster
ansible-playbook -i inventories/multinode.yml playbooks/configure-static-ips.yml
```

### Reset Cluster
```bash
# Single-pi
ansible-playbook -i inventories/single-pi.yml playbooks/k3s-reset.yml

# Multi-node
ansible-playbook -i inventories/multinode.yml playbooks/k3s-reset.yml
```

### Check Cluster Status
```bash
# After installation, kubeconfig is saved to ../kubeconfig
export KUBECONFIG=$(pwd)/../kubeconfig
kubectl get nodes
kubectl get pods -A
```

## Adding a New Cluster Type

If you need a different cluster configuration (e.g., 3-master HA):

1. Create inventory file:
   ```bash
   cp inventories/multinode.yml inventories/ha-3master.yml
   # Edit to add your nodes
   ```

2. Create group variables:
   ```bash
   mkdir -p group_vars/ha-3master
   cp group_vars/multinode/all.yml group_vars/ha-3master/all.yml
   # Edit for your HA configuration
   ```

3. Update `additional_masters` in inventory (or master args if needed)

4. Run installation:
   ```bash
   ansible-playbook -i inventories/ha-3master.yml playbooks/k3s-install.yml
   ```

## Troubleshooting

### "inventory hostname could not be matched"
Make sure you're using the correct inventory file:
```bash
# Wrong (uses default inventory.yml)
ansible-playbook playbooks/k3s-install.yml

# Correct
ansible-playbook -i inventories/single-pi.yml playbooks/k3s-install.yml
```

### Configuration not applying
Verify the cluster type is correct:
```bash
ansible-inventory -i inventories/multinode.yml --host pi-02
# Should show correct variables from group_vars/multinode/all.yml
```

### Wrong K3s version installed
Check which inventory/vars were used, then update the correct file:
```bash
# Check what was used
grep "k3s_version" group_vars/*/all.yml
```

## Notes

- **Single-Pi:** No HA support, no cluster-init, simpler networking
- **Multi-Node:** HA-ready with cluster-init, worker taints, production features
- Both clusters use the same playbooks, just different inventories and variables
- When migrating between clusters, ensure SSH keys are available for all nodes
