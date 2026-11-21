"""Build a fresh offline bundle from verified wheels and this source checkout.

Requires the pinned requirements-build.lock in the active Python environment.
No network calls are made. The Python interpreter and Docker image are external.
"""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile
from email.parser import BytesParser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheelhouse', type=Path)
    parser.add_argument('output', type=Path, help='new directory; must not exist')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output.exists():
        parser.error('output already exists')
    if sys.version_info[:2] != (3, 11):
        parser.error('build with Python 3.11')
    if version('setuptools') != '80.9.0' or version('wheel') != '0.45.1':
        parser.error('install requirements-build.lock first')
    expected = {}
    for lock in ('requirements-build.lock', 'requirements-dev.lock'):
        for line in (root / lock).read_text().splitlines():
            if not line or line.startswith('#'):
                continue
            match = re.fullmatch(r'([\w.-]+)==([\w.]+)(?:;.*)? --hash=sha256:([a-f0-9]{64})', line)
            if not match:
                parser.error(f'unsupported lock entry: {line}')
            name, release, digest = match.groups()
            expected[(name.lower().replace('-', '_'), release)] = digest
    available = {}
    for path in args.wheelhouse.glob('*.whl'):
        if not path.name.endswith('-none-any.whl'):
            continue
        with ZipFile(path) as archive:
            metadata = BytesParser().parsebytes(archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))))
        key = (metadata['Name'].lower().replace('-', '_'), metadata['Version'])
        if key in expected and hashlib.sha256(path.read_bytes()).hexdigest() == expected[key]:
            available[key] = path
    if set(available) != set(expected):
        parser.error(f'missing or changed locked wheels: {sorted(set(expected) - set(available))}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ledgergym-build-', dir=output.parent) as temp:
        stage = Path(temp) / 'bundle'
        build_root = Path(temp) / 'checkout'
        build_root.mkdir()
        # Build in a fresh tree so old build/ or egg-info files cannot enter it.
        for name in ('ledgergym', 'tests', 'examples', 'docs', 'scripts', 'third_party_licenses'):
            shutil.copytree(root / name, build_root / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('judge_adapter.py', 'requirements-role3-test.txt', 'pyproject.toml', 'MANIFEST.in', '.python-version', 'README.md', 'THIRD_PARTY_NOTICES.md', 'requirements-build.lock', 'requirements-dev.lock'):
            shutil.copy2(root / name, build_root / name)
        wheels, sources = stage / 'wheels', stage / 'source'
        wheels.mkdir(parents=True)
        sources.mkdir()
        for path in available.values():
            shutil.copy2(path, wheels / path.name)
        subprocess.run([sys.executable, '-c', 'from setuptools.build_meta import build_wheel, build_sdist; import sys; wheel_dir, source_dir = sys.argv[1:]; build_wheel(wheel_dir); build_sdist(source_dir)', str(wheels), str(sources)], cwd=build_root, check=True)
        project_wheel, = wheels.glob('ledgergym-*.whl')
        project_version = project_wheel.name.split('-')[1]
        if not (sources / f'ledgergym-{project_version}.tar.gz').is_file():
            raise RuntimeError('source distribution was not produced')
        digest = hashlib.sha256(project_wheel.read_bytes()).hexdigest()
        (stage / 'requirements-runtime.lock').write_text(f'ledgergym=={project_version} --hash=sha256:{digest}\n')
        for name in ('requirements-build.lock', 'requirements-dev.lock', 'THIRD_PARTY_NOTICES.md'):
            shutil.copy2(root / name, stage / name)
        for name in ('tests', 'examples', 'docs', 'third_party_licenses'):
            shutil.copytree(root / name, stage / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copy2(root / 'docs/OFFLINE_INSTALL.md', stage / 'README.md')
        shutil.copy2(root / 'scripts/verify_bundle.py', stage / 'verify_bundle.py')
        files = {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage / 'SHA256SUMS.json').write_text(json.dumps({'format': 'ledgergym-offline-bundle-v1', 'version': project_version, 'files': files}, indent=2, sort_keys=True)+'\n')
        # Refuse an output created while the build was running, even if empty.
        output.mkdir()
        try:
            shutil.copytree(stage, output, dirs_exist_ok=True)
        except BaseException:
            shutil.rmtree(output)
            raise
    print(json.dumps({'output': str(output), 'version': project_version, 'files': len(files)}))


if __name__ == '__main__':
    main()
