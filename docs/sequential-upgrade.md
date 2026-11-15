# Sequential homelab upgrades

The observed nine-node homelab has one SQLite control-plane server, eight
agents, and fuse-overlayfs. Some older configuration examples describe an HA
etcd setup; do not replay them over the live server during an upgrade.

Use the official K3s manual binary upgrade method to preserve the active
systemd units and environment. Do not run reset, uninstall or killall scripts
as part of a normal version upgrade.
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

## Recovery observed during the 1.31 runtime transition

On pi-03, containerd garbage collection encountered an abandoned fuse-overlayfs
snapshot containing over 1.8 million `gosnowflake-cgo*` temporary files. The
snapshotter held its write lock while deleting them from the SD card, blocking
all new containers. Timed-out requests then produced stale container/sandbox
name reservations. Increasing application startup deadlines would not resolve
this runtime lock.

The diagnostic was a containerd SIGUSR1 goroutine dump: snapshot creation waited
on `snapshotter.createSnapshot` while garbage collection was in
`fuse-overlayfs-snapshotter.Remove` / `os.RemoveAll`. Do not mistake this for a
full disk or delete live snapshot directories.

Recovery stopped the agent, confirmed containerd had exited and the discarded
snapshot had no mount-namespace references, copied both containerd metadata
databases, and renamed only that already-discarded snapshot into
`/var/lib/rancher/k3s/agent/gc-quarantine-20261115/89656`. Its remaining contents
were preserved outside the snapshotter's managed directory. Starting the agent
then allowed new containers to start. This is incident-specific recovery, not
a general instruction to move snapshot directories during upgrades.

Vault required manual unseal after its container restarted. A fresh restricted
test pod on pi-03 verified cluster DNS, the custom Authentik-to-Traefik DNS
rewrite and writable ephemeral storage. Seerr's replacement pod also confirmed
installation of the existing request-scoped season-search patch. Keep the
quarantine and private diagnostic/metadata backups until separately reviewed.

## Corrupt worker runtime catalog recovery

During the 1.33 control-plane step, `raspberrypi-51249e4e` (still on 1.32)
failed to start new containers. Containerd repeatedly panicked while reading
page 699 of the fuse-overlayfs snapshot catalog. The node's existing container
processes initially survived, so pod readiness alone did not reveal the crash
loop. Check the actual agent service and fresh pod creation when diagnosing a
stalled upgrade.

The rollout was stopped and that worker cordoned. Recovery saved the runtime
metadata, a logical AI PostgreSQL dump and an offline archive of both local
application PVC directories. PostgreSQL was stopped with its fast-shutdown
signal. The views service did not exit on TERM; its JSON data was backed up and
validated before terminating it. The offline archive was verified by reading
all members.

Only after these backups, the node-local `k3s-killall.sh` was used to clean up
the failed runtime and mounts. With no runtime processes or mounts remaining,
`agent/containerd` was renamed to `agent/containerd-corrupt-20261115`, retaining
the damaged cache for investigation. Restarting the same K3s agent recreates
the disposable runtime cache and pulls images again. The application data in
`/var/lib/rancher/k3s/storage` is left in place. Never remove that storage tree,
uninstall K3s, or apply this recovery to a server datastore.

References: https://docs.k3s.io/upgrades/manual and
https://docs.k3s.io/datastore/backup-restore
