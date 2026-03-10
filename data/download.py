"""
Download SF-133 Excel files from the OMB MAX portal.

Reads file_registry.json to determine URLs, downloads to data/cache/,
and skips files that already exist unless --force is specified.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
REGISTRY_PATH = PROJECT_ROOT / "file_registry.json"
BASE_URL = "https://portal.max.gov/portal/document/SF133/Budget/attachments"


def load_registry() -> dict:
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def download_file(url: str, dest: Path, force: bool = False) -> bool:
    """Download a single file. Returns True if downloaded, False if skipped."""
    if dest.exists() and not force:
        return False

    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return True


def download_all(
    fiscal_years: list[int] | None = None,
    file_keys: list[str] | None = None,
    force: bool = False,
) -> dict[str, Path]:
    """
    Download SF-133 files for specified fiscal years and agency file keys.

    Returns a dict mapping "YYYY/key" to the local file path.
    """
    registry = load_registry()
    downloaded = {}

    for fy_str, fy_info in registry.items():
        fy = int(fy_str)
        if fiscal_years is not None and fy not in fiscal_years:
            continue

        attachment_id = fy_info["attachment_id"]
        files = fy_info["files"]

        for key, filename in files.items():
            if file_keys is not None and key not in file_keys:
                continue

            url = f"{BASE_URL}/{attachment_id}/{filename}"
            dest = CACHE_DIR / f"FY{fy}" / filename
            label = f"FY{fy}/{key}"

            try:
                was_downloaded = download_file(url, dest, force=force)
                status = "downloaded" if was_downloaded else "cached"
                print(f"  [{status}] {label}: {dest.name}")
                downloaded[label] = dest
            except requests.HTTPError as e:
                print(f"  [ERROR] {label}: {e}", file=sys.stderr)
            except requests.ConnectionError as e:
                print(f"  [ERROR] {label}: connection failed", file=sys.stderr)

    return downloaded


def get_local_path(fiscal_year: int, file_key: str) -> Path | None:
    """Get the local cache path for a specific FY/agency file, or None if not available."""
    registry = load_registry()
    fy_str = str(fiscal_year)
    if fy_str not in registry:
        return None
    files = registry[fy_str].get("files", {})
    if file_key not in files:
        return None
    path = CACHE_DIR / f"FY{fiscal_year}" / files[file_key]
    return path if path.exists() else None


def list_available() -> list[tuple[int, str, bool]]:
    """List all registry entries and whether they are cached locally."""
    registry = load_registry()
    result = []
    for fy_str, fy_info in sorted(registry.items()):
        for key in sorted(fy_info.get("files", {})):
            path = get_local_path(int(fy_str), key)
            result.append((int(fy_str), key, path is not None))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download SF-133 data files")
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    parser.add_argument("--years", nargs="*", type=int, help="Specific fiscal years")
    parser.add_argument("--agencies", nargs="*", help="Specific file keys (hhs, nsf, etc.)")
    parser.add_argument("--list", action="store_true", help="List available files")
    args = parser.parse_args()

    if args.list:
        for fy, key, cached in list_available():
            status = "cached" if cached else "missing"
            print(f"  FY{fy}/{key}: {status}")
    else:
        print("Downloading SF-133 files...")
        results = download_all(
            fiscal_years=args.years,
            file_keys=args.agencies,
            force=args.force,
        )
        print(f"\nDone. {len(results)} files ready.")
