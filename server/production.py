#!/usr/bin/env python3
"""Start the private gateway with a verified, route-restricted router key."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'server')]

def main():
    path = Path(os.environ.get('ATLAS_CONFIG_PATH', str(ROOT / 'config/final.yaml')))
    raw = path.read_text()
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        import yaml
        config = yaml.safe_load(raw)
    model = config['model']
    from router_client import prepare_router_key
    prepare_router_key(os.environ.get('ATLAS_CHAT_PRIMARY') or model['primary_model'],
                       [os.environ.get('ATLAS_CHAT_FALLBACK') or model['fallback_model']])
    from gateway import main as serve
    serve()

if __name__ == '__main__':
    main()
