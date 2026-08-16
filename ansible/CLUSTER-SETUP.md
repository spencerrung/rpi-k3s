# Cluster Configuration Guide

This directory supports multiple K3s cluster configurations. Choose the one that matches your setup.

## Available Clusters

### Single-Node RPi5 (Development/Testing)
- **Inventory:** `inventories/single-pi.yml`
- **Configuration:** `group_vars/single_pi/all.yml`
- **Usage:** Single Raspberry Pi 5 for development and testing
- **HA Enabled:** No

**Install:**
```bash
ansible-playbook -i inventories/single-pi.yml playbooks/k3s-install.yml
```

### Multi-Node Production (8 Workers + 1 Master)
- **Inventory:** `inventories/multinode.yml`
- **Configuration:** `group_vars/multinode/all.yml`
- **Usage:** Production workloads across 9 Raspberry Pis
- **Current state:** One primary master and eight workers; HA migration has not been performed

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
│   ├── single_pi/all.yml        # Single-pi cluster config
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

## Future HA Operations

The following operations are preparation for a future migration window. Do not
run them against the live cluster until the HA change is scheduled.

### Migrate the Existing Primary to HA

Run this once for the existing single-server cluster. It briefly interrupts
the API and requires the exact confirmation string:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/migrate-single-server-to-ha.yml \
  --limit pi-01 \
  -e migration_confirmation=MIGRATE_K3S_SQLITE_TO_ETCD
```

### Promote an Existing Worker

Use this for a worker that is already running K3s. It drains the node and
reinstalls it as a server; it is not the same operation as adding a fresh
additional master:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/promote-worker-to-master.yml \
  --limit pi-06 \
  -e promotion_confirmation=PROMOTE_K3S_WORKER_TO_MASTER
```

### Add Fresh Masters

After migration, add fresh nodes under the sibling `additional_masters` group
and run:

```bash
ansible-playbook -i inventories/multinode.yml playbooks/add-masters.yml
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

3. Keep the cluster-specific group name aligned with the directory name and
   update `additional_masters` in inventory if needed

4. Run installation:
   ```bash
   ansible-playbook -i inventories/ha-3master.yml playbooks/k3s-install.yml
   ```

## Troubleshooting

### "inventory hostname could not be matched"
Make sure you're using the correct inventory file:
```bash
# Wrong (no explicit inventory)
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
- **Multi-Node:** Currently one primary plus eight workers; HA migration tooling is available but not active
- Both clusters use the same playbooks, just different inventories and variables
- When migrating between clusters, ensure SSH keys are available for all nodes
