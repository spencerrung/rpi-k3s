#!/usr/bin/env python3
"""One minor hop for the existing ARM64, single-SQLite-server homelab.

Uses the server's matching kubectl, preserves systemd arguments, never drains
local-PV workloads, and leaves a failed node cordoned for investigation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time


def version(value):
    m = re.fullmatch(r'v1\.(\d+)\.(\d+)\+k3s(\d+)', value)
    if not m:
        raise ValueError('Expected a stable K3s v1 minor/patch version')
    return tuple(map(int, m.groups()))


def valid_hop(current, target):
    a, b = version(current), version(target)
    return b > a and b[0] in (a[0], a[0] + 1)


class Upgrade:
    def __init__(self, args):
        self.a = args
        self.ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                    '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=4',
                    '-i', args.key]
        self.root = Path(args.backup_dir).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def remote(self, ip, command, **kwargs):
        return subprocess.check_output(self.ssh + ['pi@' + ip, command],
                                       timeout=kwargs.pop('timeout', 180), **kwargs)

    def kube(self, *args):
        return self.remote(self.a.server, 'sudo -n k3s kubectl --request-timeout=30s ' +
                           shlex.join(args), stderr=subprocess.DEVNULL)

    def nodes(self):
        return json.loads(self.kube('get', 'nodes', '-o', 'json'))['items']

    def wait(self, label, predicate, timeout=900):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if predicate():
                    print(label + ': OK', flush=True)
                    return
            except (subprocess.SubprocessError, ValueError, KeyError):
                pass
            time.sleep(10)
        raise RuntimeError(label + ': timed out; stop and investigate')

    def healthy(self):
        self.kube('get', '--raw=/readyz')
        nodes = self.nodes()
        if not all(any(c['type'] == 'Ready' and c['status'] == 'True'
                       for c in n['status']['conditions']) for n in nodes):
            return False
        items = json.loads(self.kube('get', 'deploy,sts,ds', '-A', '-o', 'json'))['items']
        for x in items:
            s = x.get('status', {})
            desired = s.get('desiredNumberScheduled', 0) if x['kind'] == 'DaemonSet' else x['spec'].get('replicas', 1)
            ready = s.get('numberReady', 0) if x['kind'] == 'DaemonSet' else s.get('readyReplicas', 0)
            if ready < desired:
                return False
        return True

    def backup_server(self):
        stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        remote = '/var/backups/k3s-upgrade/' + stamp + '-' + self.a.version
        code = '''import pathlib,sqlite3,shutil,os
os.umask(0o077)
p=pathlib.Path(REMOTE);p.mkdir(parents=True)
root=pathlib.Path('/var/lib/rancher/k3s/server')
assert (root/'db/state.db').exists() and not (root/'db/etcd/member').exists(), 'Not a SQLite server'
s=sqlite3.connect(root/'db/state.db');d=sqlite3.connect(p/'state.db');s.backup(d)
assert d.execute('pragma integrity_check').fetchone()[0]=='ok'
d.close();s.close()
shutil.copy2(root/'token',p/'token')
shutil.copy2('/usr/local/bin/k3s',p/'k3s.previous')
for src in ['/etc/rancher/k3s','/etc/systemd/system/k3s.service','/etc/systemd/system/k3s.service.env']:
 src=pathlib.Path(src)
 if src.exists():
  if src.is_dir():shutil.copytree(src,p/src.name)
  else:shutil.copy2(src,p/src.name)
print('Consistent SQLite backup and token saved')
'''.replace('REMOTE', repr(remote))
        self.remote(self.a.server, 'sudo -n python3 -', input=code.encode())
        dest = self.root / (stamp + '-' + self.a.version + '-server.tar.gz')
        with dest.open('wb') as f:
            subprocess.run(self.ssh + ['pi@' + self.a.server,
                           'sudo -n tar -czf - -C ' + shlex.quote(remote) + ' .'],
                           stdout=f, check=True, timeout=600)
        # Verify the off-host archive is readable before changing the server.
        import tarfile
        with tarfile.open(dest) as archive:
            names = archive.getnames()
            assert './state.db' in names and './token' in names
            for member in archive:
                if member.isfile():
                    stream = archive.extractfile(member)
                    while stream.read(1024 * 1024):
                        pass
        print('Verified off-host recovery archive: ' + str(dest), flush=True)

    def run(self):
        target = self.a.version
        version(target)
        nodes = self.nodes()
        servers = [n for n in nodes if 'node-role.kubernetes.io/control-plane' in n['metadata']['labels']]
        assert len(servers) == 1, 'This procedure is for one SQLite server only'
        ip = lambda n: next(x['address'] for x in n['status']['addresses'] if x['type'] == 'InternalIP')
        assert ip(servers[0]) == self.a.server
        ordered = servers + sorted([n for n in nodes if n not in servers], key=lambda n: n['metadata']['name'])
        for n in ordered:
            current = n['status']['nodeInfo']['kubeletVersion']
            assert current == target or valid_hop(current, target), f'Unsafe version hop: {current} -> {target}'
            assert not n['spec'].get('unschedulable'), 'Resolve existing cordons before continuing'
            print(n['metadata']['name'], current, '->', target, flush=True)
        binary = self.root / 'binaries' / target / 'k3s-arm64'
        sha = (binary.parent / 'sha256').read_text().strip()
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == sha
        if not self.a.execute:
            print('Read-only preflight passed; --execute is required for changes')
            return
        self.wait('Initial workload health', self.healthy)
        self.backup_server()
        for n in ordered:
            name, address = n['metadata']['name'], ip(n)
            if n['status']['nodeInfo']['kubeletVersion'] == target:
                continue
            service = 'k3s' if n in servers else 'k3s-agent'
            # Assert platform and free disk space before staging a new binary.
            check = "import platform,shutil;assert platform.machine()=='aarch64';assert shutil.disk_usage('/usr/local/bin').free>1024**3"
            self.remote(address, 'sudo -n python3 -c ' + shlex.quote(check))
            staged = '/tmp/homelab-k3s-' + target
            subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', '-i', self.a.key,
                            str(binary), 'pi@' + address + ':' + staged], check=True, timeout=300)
            self.kube('cordon', name)
            print('Upgrading ' + name + ' (' + service + ')', flush=True)
            cmd = f'''set -eu
printf '%s  %s\\n' {shlex.quote(sha)} {shlex.quote(staged)} | sha256sum -c - >/dev/null
sudo -n install -m 0755 {shlex.quote(staged)} /usr/local/bin/k3s.upgrade
sudo -n cp -p /usr/local/bin/k3s /usr/local/bin/k3s.previous
sudo -n mv /usr/local/bin/k3s.upgrade /usr/local/bin/k3s
sudo -n systemctl restart {service}
rm {shlex.quote(staged)}
'''
            self.remote(address, cmd, timeout=600)
            def node_ready():
                node = next(x for x in self.nodes() if x['metadata']['name'] == name)
                return node['status']['nodeInfo']['kubeletVersion'] == target and any(
                    c['type'] == 'Ready' and c['status'] == 'True' for c in node['status']['conditions'])
            self.wait(name + ' reports target version and Ready', node_ready)
            self.kube('uncordon', name)
            self.wait(name + ' workload recovery', self.healthy)
            (self.root / 'last-success.json').write_text(json.dumps({'version': target, 'node': name, 'time': time.time()}))
        self.kube('exec', '-n', 'media', 'deploy/sonarr', '-c', 'sonarr', '--',
                  'getent', 'hosts', 'kubernetes.default.svc.cluster.local')
        print('COMPLETE: all nodes on ' + target + '; API, workloads and cluster DNS healthy', flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', required=True)
    p.add_argument('--server', required=True)
    p.add_argument('--key', required=True)
    p.add_argument('--backup-dir', required=True)
    p.add_argument('--execute', action='store_true')
    Upgrade(p.parse_args()).run()
