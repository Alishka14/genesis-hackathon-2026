"""Check every delivered file against the bundle's SHA-256 manifest."""
import hashlib
import json
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'SHA256SUMS.json').read_text())
    expected = manifest['files']
    for name, digest in expected.items():
        path = root / name
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise SystemExit(f'Invalid bundle path: {name}')
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SystemExit(f'Missing or changed file: {name}')
    print(json.dumps({'verified_files': len(expected), 'python': sys.version.split()[0]}))


if __name__ == '__main__':
    main()
