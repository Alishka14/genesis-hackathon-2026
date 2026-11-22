"""Verify the *complete* offline artifact inventory and all SHA-256 hashes.

The SHA256SUMS.json manifest itself is not signed: this detects accidental
modifications and unexpected files, not malicious replacement by a party that
can edit both the manifest and its contents.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def verify_bundle(root):
    root = Path(root).resolve(strict=True)
    manifest_file = root / 'SHA256SUMS.json'
    if not manifest_file.is_file() or manifest_file.is_symlink():
        raise ValueError('Missing or linked SHA256SUMS.json')
    try:
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise ValueError('Unreadable SHA256SUMS.json') from exc
    if (not isinstance(manifest, dict)
            or set(manifest) != {'format', 'version', 'files'}
            or manifest['format'] != 'ledgergym-offline-bundle-v1'
            or not isinstance(manifest['version'], str)
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+\.dev[0-9]+', manifest['version'])
            or not isinstance(manifest['files'], dict)
            or not manifest['files']):
        raise ValueError('Invalid bundle manifest schema')
    expected = manifest['files']
    for name, digest in expected.items():
        if (not isinstance(name, str) or not name
                or PurePosixPath(name).is_absolute()
                or '\\' in name or any(part in ('', '.', '..') for part in name.split('/'))
                or name == 'SHA256SUMS.json'
                or not isinstance(digest, str)
                or not re.fullmatch(r'[a-f0-9]{64}', digest)):
            raise ValueError('Invalid bundle path or digest')
    found = set()
    for item in root.rglob('*'):
        if item.is_symlink():
            raise ValueError(f'Linked bundle entry: {item.relative_to(root)}')
        if item.is_file():
            name = item.relative_to(root).as_posix()
            if name != 'SHA256SUMS.json':
                found.add(name)
        elif not item.is_dir():
            raise ValueError(f'Unsupported bundle entry: {item.relative_to(root)}')
    if found != set(expected):
        missing = sorted(set(expected) - found)
        extra = sorted(found - set(expected))
        raise ValueError(f'Bundle inventory differs: missing={missing[:5]} extra={extra[:5]}')
    for name, digest in expected.items():
        path = root / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Missing or changed file: {name}')
    return {'verified_files': len(expected), 'version': manifest['version'],
            'python': sys.version.split()[0]}


def main():
    argparse.ArgumentParser(
        description='Verify the offline bundle that contains this script: every file '
                    'listed in SHA256SUMS.json, no extra files and all SHA-256 hashes. '
                    'Run it from inside a built bundle; it takes no arguments.',
    ).parse_args()
    try:
        report = verify_bundle(Path(__file__).resolve().parent)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    main()
