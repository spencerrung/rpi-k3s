# Sequential homelab upgrades

The observed nine-node homelab has one SQLite control-plane server, eight
agents, and fuse-overlayfs. Some older configuration examples describe an HA
etcd setup; do not replay them over the live server during an upgrade.

Use the official K3s manual binary upgrade method to preserve the active
systemd units and environment. Do not run reset, uninstall or killall scripts.
A brief control-plane interruption is expected because there is one server.

For each target, download `k3s-arm64` and `sha256sum-arm64.txt` from that
specific official GitHub release. Verify SHA256 and put the binary plus its
checksum in `<backup-dir>/binaries/<version>/{k3s-arm64,sha256}`. Then:

```sh
python3 scripts/upgrade-homelab.py --version v1.30.14+k3s2 \
  --server 10.10.10.230 --key ~/.ssh/raspberrypi_rsa \
  --backup-dir ~/homelab-backups/k3s-20261115
# Review preflight output; the same command with --execute performs the hop.
```

The November 2026 path is 1.29.10 -> 1.30.14+k3s2 -> 1.31.14+k3s1 ->
1.32.13+k3s1 -> 1.33.13+k3s2 -> 1.34.13+k3s1 -> 1.35.10+k3s1 ->
1.36.6+k3s1 -> 1.37.2+k3s1. Never skip a minor. Upgrade compatible Flux
releases as Kubernetes reaches their supported versions.

Each hop backs up SQLite consistently, validates its integrity, preserves the
server token, config and previous binary, and verifies an off-host archive.
Backups contain secrets and must stay outside Git with restrictive permissions.
Every node is cordoned, its binary is replaced atomically, and its existing
service is restarted. Pods are not drained because several use node-local
PVCs; containers normally survive the K3s restart. Node version/readiness,
workload readiness and cluster DNS are checked before proceeding.

A failed step leaves the affected node cordoned. Inspect the service and
cluster before resuming; do not blindly uncordon or continue. The script can
resume a partial hop after recovery and skips nodes already at the target.
If a server database migration needs reversal, stop K3s and restore the
matching database, token and old binary together. Do not downgrade the binary
against a migrated database. Preserve failed state before restoring anything.

Two agents (10.10.10.218 and 10.10.10.122) had obsolete server units repeatedly
failing with `etcd disabled`. Their unit/environment files were backed up and
only the failed server services disabled; their healthy agent services remain.

References: https://docs.k3s.io/upgrades/manual and
https://docs.k3s.io/datastore/backup-restore
