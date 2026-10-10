"""Verify preserved originals against the recorded inventory and Git exclusions."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
inventory = json.loads((root / 'notes/source-inventory.json').read_text())
failures = []
for item in inventory['files']:
    p = root / item['path']
    if not p.is_file():
        failures.append(f"Missing: {item['path']}")
        continue
    if p.stat().st_size != item['bytes']:
        failures.append(f"Size changed: {item['path']}")
    if hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']:
        failures.append(f"Checksum changed: {item['path']}")

archive_files = sorted(p for p in (root / 'archive').rglob('*') if p.is_file())
paths = [str(p.relative_to(root)) for p in archive_files]
if paths:
    ignored = subprocess.run(['git', 'check-ignore', '--stdin', '-z'], cwd=root,
        input=('\0'.join(paths) + '\0').encode(), capture_output=True, check=False)
    ignored_paths = set(ignored.stdout.decode().split('\0'))
    failures.extend(f'Not gitignored: {p}' for p in paths if p not in ignored_paths)
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
for name in filter(None, tracked):
    p = root / name
    if name.startswith('archive/'):
        failures.append(f'Archive file tracked by Git: {name}')
    if p.is_file() and p.stat().st_size > 5 * 1024 * 1024:
        failures.append(f'Tracked file exceeds 5 MiB: {name}')

messages_path = root / 'archive/discord/messages.json'
if messages_path.exists():
    capture = json.loads(messages_path.read_text())
    ids = [m['id'] for m in capture['messages']]
    if len(ids) != 25 or len(set(ids)) != 25:
        failures.append('Expected the recorded 25-message snapshot; review any new snapshot explicitly.')
    if len(capture['attachments']) != 9:
        failures.append('Expected nine original attachments.')
else:
    failures.append('Missing local Discord message export.')

full_manifest = root / 'archive/checksums.json'
if full_manifest.exists():
    for item in json.loads(full_manifest.read_text())['files']:
        p = root / item['path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']:
            failures.append(f"Local archive file missing or changed: {item['path']}")

if failures:
    print('\n'.join(failures), file=sys.stderr)
    sys.exit(1)
print(f"Verified {len(inventory['files'])} inventoried source files, 25 messages, 9 attachments.")
print(f'All {len(paths)} archive files are ignored; no archived or >5 MiB files tracked.')
if full_manifest.exists():
    print('All files in the full local checksum manifest match.')
