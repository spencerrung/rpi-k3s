# K3s High Availability Setup

This repository supports two HA operations:

1. Convert the existing single-server SQLite cluster to embedded etcd.
2. Add fresh servers or explicitly promote existing workers.

The SQLite conversion briefly interrupts the Kubernetes API. Do not describe
that step as zero-downtime maintenance.

## Requirements

- The current primary is healthy and reachable over SSH.
- The final embedded-etcd server count is odd: 3, 5, or 7.
- All servers can reach each other on the K3s server and embedded-etcd ports.
- Fresh server targets have static IPs and no existing K3s installation.
- Existing workers are promoted separately and one at a time.

## 1. Convert the Existing Primary

K3s supports converting an existing SQLite server by restarting it with
`cluster-init`. This repository makes that an explicit, guarded operation.

Run from `ansible/`:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/migrate-single-server-to-ha.yml \
  --limit pi-01 \
  -e migration_confirmation=MIGRATE_K3S_SQLITE_TO_ETCD
```

The playbook:

- requires exactly one primary target and an exact confirmation string;
- checks that the server is currently active and using SQLite;
- stops K3s and archives `state.db` plus SQLite sidecar files;
- fetches the archive to `ansible/backups/` with restrictive permissions;
- enables `cluster-init` in the K3s config;
- restarts K3s and verifies the API and embedded-etcd member database.

Move the fetched archive to separate backup storage before continuing. If the
migration fails, preserve the archive and inspect the service and journal
before retrying.

Reference: https://docs.k3s.io/datastore/ha-embedded

## 2. Configure the Inventory

Fresh additional servers belong in the sibling `additional_masters` group in
`ansible/inventories/multinode.yml`; they must not be nested under
`k3s_cluster` before joining:

```yaml
additional_masters:
  hosts:
    pi-06:
      ansible_host: 10.10.10.50
      ansible_user: pi
      ansible_ssh_private_key_file: ~/.ssh/raspberrypi_rsa
      k3s_node_name_override: raspberrypi-new-1
    pi-07:
      ansible_host: 10.10.10.51
      ansible_user: pi
      ansible_ssh_private_key_file: ~/.ssh/raspberrypi_rsa
      k3s_node_name_override: raspberrypi-new-2
```

The node-name override is only needed when the inventory alias differs from
the Linux/Kubernetes node name.

Existing workers are not fresh targets. Promote them with the guarded workflow
below instead of putting them in `additional_masters`.

## 3. Promote an Existing Worker

Promotion drains the worker, uninstalls its K3s agent, and installs it as a
server. It is destructive to the agent installation and must be done one node
at a time:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/promote-worker-to-master.yml \
  --limit pi-06 \
  -e promotion_confirmation=PROMOTE_K3S_WORKER_TO_MASTER
```

The playbook refuses targets with an existing server service and refuses to
continue when node-local storage is present unless this risk is explicitly
acknowledged:

```bash
-e acknowledge_local_storage_risk=true
```

That flag is not a backup. Back up or migrate local-path data first.

## 4. Add Fresh Servers

After the primary has been migrated, add fresh targets with:

```bash
ansible-playbook -i inventories/multinode.yml \
  playbooks/add-masters.yml
```

The playbook refuses a non-HA primary, requires an odd final server count,
serializes joins, protects the server token from output, and verifies each
joined node by its Kubernetes name.

## Stable API and Worker Registration

Control-plane redundancy is not the same as end-to-end worker availability.
Existing workers and kubeconfigs still point at the original primary unless a
stable registration address is configured.

For a load balancer or VIP, set it before installing new nodes:

```yaml
k3s_registration_address: 10.10.10.50
k3s_tls_sans:
  - 10.10.10.50
```

The address must be reachable from every server and worker. `k3s_tls_sans`
is required for a registration address that is not already a server address.
After the endpoint is ready, update existing worker service environment files
and kubeconfigs, then restart the agents.

## Verification

```bash
kubectl get nodes -o wide
kubectl get nodes -l node-role.kubernetes.io/control-plane
sudo k3s etcd-snapshot ls
sudo test -d /var/lib/rancher/k3s/server/db/etcd/member
```

Embedded etcd is part of the K3s server process; it is not a normal
`component=etcd` pod.

## Rollback and Removal

Do not remove a server from an embedded-etcd cluster without checking quorum.
Keep at least two healthy members while removing one member, and take an etcd
snapshot first. The existing `k3s-reset.yml` is a full destructive reset, not
a server-removal workflow.

## Troubleshooting

```bash
sudo systemctl status k3s
sudo journalctl -u k3s -n 100 --no-pager
kubectl get nodes -o wide
kubectl get events --sort-by=.lastTimestamp
```

For token details and backup requirements, see:
https://docs.k3s.io/cli/token
