"""
Shared SDE (Static Data Export) loading utilities.
Provides cached YAML loading and file-search helpers used by multiple scripts.
"""

import os
import pickle
import yaml
from pathlib import Path

from tools.config import SDE_DIR


def get_yaml_loader():
    """Return the fastest available YAML loader."""
    return yaml.CSafeLoader if hasattr(yaml, 'CSafeLoader') else yaml.SafeLoader


def find_sde_file(filename: str) -> Path | None:
    """Recursively search for a file inside SDE_DIR. Returns Path or None."""
    for root, _dirs, files in os.walk(SDE_DIR):
        if filename in files:
            return Path(root) / filename
    return None


def load_cached_yaml(yaml_path: Path, cache_name: str, display_name: str) -> dict:
    """
    Load a YAML file from the SDE with a pickle cache for speed.

    On first load, parses YAML and stores a .pkl file next to the source.
    On subsequent loads, returns the pkl (10-20x faster than YAML parsing).

    Args:
        yaml_path:    Absolute Path to the .yaml source file.
        cache_name:   Filename (not path) for the .pkl cache, stored in SDE_DIR.
        display_name: Human-readable name used in progress messages.

    Returns:
        Parsed dict (from pkl or YAML).

    Raises:
        FileNotFoundError: If yaml_path does not exist and no cache is found.
    """
    cache_path = SDE_DIR / cache_name

    # Use cache when it's newer than the source YAML
    if cache_path.exists():
        if not yaml_path.exists() or cache_path.stat().st_mtime > yaml_path.stat().st_mtime:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            print(f"   ✓ Loaded {len(data):,} {display_name} entries from cache")
            return data

    if not yaml_path.exists():
        raise FileNotFoundError(f"{display_name} not found: {yaml_path}")

    print(f"   Parsing {display_name} (first time may take 30-90 seconds)...")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.load(f, Loader=get_yaml_loader())

    SDE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'wb') as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"   ✓ Loaded {len(data):,} {display_name} entries from YAML")
    return data
