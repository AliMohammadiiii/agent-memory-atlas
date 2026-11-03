"""Server-only runtime: reuse process environment, never copy credential files."""
import os
import subprocess
from pathlib import Path


def inherit_research_credentials():
    wanted = ('JINA_API_KEY', 'OPENROUTER_API_KEY')
    if all(os.environ.get(k) for k in wanted): return
    try:
        pid = int(subprocess.check_output(['systemctl', 'show', 'alimohamadi-me-mbse.service', '--property=MainPID', '--value']))
        entries = Path('/proc').joinpath(str(pid), 'environ').read_bytes().split(b'\0')
        environment = dict(item.split(b'=', 1) for item in entries if b'=' in item)
        for key in wanted:
            if not os.environ.get(key) and environment.get(key.encode()): os.environ[key] = environment[key.encode()].decode()
    except (OSError, ValueError, subprocess.SubprocessError):
        pass


def private_root():
    value = os.environ.get('ATLAS_PRIVATE_DIR')
    if not value: raise RuntimeError('Set ATLAS_PRIVATE_DIR outside the repository')
    root = Path(value).resolve()
    engine = Path(__file__).resolve().parents[1]
    if root == engine or engine in root.parents: raise RuntimeError('Private analysis must stay outside the repository')
    root.mkdir(parents=True, exist_ok=True); root.chmod(0o700)
    return root


def phase2_config():
    """Select a dated snapshot without editing shared configuration."""
    import re
    import yaml
    config = yaml.safe_load((Path(__file__).resolve().parents[1]/'config/phase2.yaml').read_text())
    snapshot = os.environ.get('ATLAS_SNAPSHOT_ID', config['snapshot'])
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[a-zA-Z0-9_-]+', snapshot):
        raise ValueError('Snapshot id must be dated and contain no path separators')
    config['snapshot'] = snapshot
    cutoff = os.environ.get('ATLAS_SNAPSHOT_CUTOFF')
    if cutoff:
        from datetime import date
        date.fromisoformat(cutoff)
        config['cutoff'] = cutoff
    return config
