"""Download all locked universal wheels for a later *network-free* release.

This preparation step MAY use the package index. It is deliberately separate
from verify_offline_release.py, which never invokes package index URLs.
The output directory must not already exist.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheelhouse', type=Path, help='NEW local wheel directory')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.wheelhouse.expanduser().resolve()
    if output.exists():
        parser.error('wheelhouse must be a NEW directory; refusing overwrite')
    with tempfile.TemporaryDirectory(prefix='ledgergym-locks-') as tmp:
        universal = Path(tmp) / 'dev-universal.lock'
        # Include Windows-only colorama when preparing a cross-platform
        # universal wheelhouse on macOS. Hashes/versions remain unchanged.
        dev_lock = (root / 'requirements-dev.lock').read_text(encoding='utf-8')
        universal.write_text(dev_lock.replace('; sys_platform == "win32"', ''), encoding='utf-8')
        output.mkdir(parents=True)
        cmd = [
            sys.executable, '-m', 'pip', 'download', '--no-deps',
            '--only-binary=:all:', '--require-hashes', '--dest', str(output),
            '-r', str(root / 'requirements-build.lock'),
            '-r', str(universal),
        ]
        try:
            subprocess.run(cmd, cwd=root, check=True)
            wheels = sorted(output.glob('*.whl'))
            if len(wheels) != 8:
                raise RuntimeError(f'expected 8 locked wheels, found {len(wheels)}')
        except BaseException:
            shutil.rmtree(output)
            raise
    print(f'Prepared {len(wheels)} hash-locked universal wheels in {output}')


if __name__ == '__main__':
    main()
