"""Copy a validated legacy query pair to a new hash-manifest cache directory."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

import numpy as np
from scripts.analytics_final import digest


def migrate(source: Path, output: Path, config: dict[str, Any], text: str) -> str:
    """Check a caller-identified legacy pair without changing its original files.

    Old files have no vector hash; their claimed origin cannot be independently authenticated.
    """
    parameters = config["embeddings"]
    key = digest({"text": text, "parameters": parameters, "task": "retrieval.query"})
    destination = output / "project-query-cache"
    if source.resolve() == destination.resolve():
        raise ValueError("Choose a different destination to preserve the original cache")
    try:
        raw = (source / (key + ".npy")).read_bytes()
        metadata = json.loads((source / (key + ".json")).read_text())
        vector = np.load(io.BytesIO(raw), allow_pickle=False)
    except (OSError, ValueError, EOFError) as exc:
        raise ValueError(f"Cannot read legacy cache pair: {exc}") from exc
    if not isinstance(metadata, dict) or "_atlas_cache" in metadata:
        raise ValueError("Invalid legacy provenance")
    if parameters.get("model") and metadata.get("model") != parameters["model"]:
        raise ValueError("Legacy provenance model does not match config")
    dimension = parameters.get("dimensions", parameters.get("dimension"))
    if (
        not isinstance(vector, np.ndarray)
        or vector.ndim != 1
        or not np.isfinite(vector).all()
        or not np.isclose(np.linalg.norm(vector), 1.0, rtol=1e-5, atol=1e-6)
        or (dimension is not None and len(vector) != dimension)
    ):
        raise ValueError(
            "Invalid legacy vector: expected finite normalized vector and matching dimension"
        )
    manifest = {
        **metadata,
        "_atlas_cache": {"key": key, "vector_sha256": hashlib.sha256(raw).hexdigest()},
    }
    destination.mkdir(parents=True, exist_ok=True)
    for suffix, data in [
        (".npy", raw),
        (".json", (json.dumps(manifest, sort_keys=True) + "\n").encode()),
    ]:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination / (key + suffix))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path, help="legacy project-query-cache folder"
    )
    parser.add_argument("--output", required=True, type=Path, help="new base folder")
    parser.add_argument(
        "--config", required=True, type=Path, help="JSON configuration containing embeddings"
    )
    parser.add_argument(
        "--text-file", required=True, type=Path, help="UTF-8 query text file; read exactly"
    )
    args = parser.parse_args()
    try:
        key = migrate(
            args.source,
            args.output,
            json.loads(args.config.read_text()),
            args.text_file.read_text(),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"cache migration: {exc}", file=sys.stderr)
        return 2
    print(f"Validated legacy pair copied under key {key}; original files unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
