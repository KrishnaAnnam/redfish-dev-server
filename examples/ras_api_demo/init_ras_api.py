#!/usr/bin/env python3
"""
Initialize RAS API - Clean up client-side output files

Clears all files from the cper_storage, cpad_storage, and Analyzer_output_files
directories under ras_demo_output/ to prepare for a fresh RAS API testing session.
Use --no-analyzer to skip clearing error history and analyzer outputs.

This is the bmc-redfish-simulator equivalent of RasApi0204/InitializeRasApi.py.

Usage:
    python scripts/initializeRasApi.py
    python scripts/initializeRasApi.py --output-dir ras_demo_output
    python scripts/initializeRasApi.py --no-analyzer
"""

import os
import sys
import shutil
import argparse
from pathlib import Path


# Resolve paths relative to this script's directory (examples/ras_api_demo/)
PROJECT_ROOT = Path(__file__).resolve().parent


def clear_directory(directory_path, dir_name):
    """
    Clear all contents from a directory.

    Args:
        directory_path: Path to the directory to clear
        dir_name: Name of the directory for display purposes

    Returns:
        Number of items deleted
    """
    if not directory_path.exists():
        print(f"  ⓘ {dir_name} does not exist: {directory_path}")
        return 0

    if not directory_path.is_dir():
        print(f"  ✗ {dir_name} is not a directory: {directory_path}")
        return 0

    deleted_count = 0

    # Delete all files and subdirectories
    for item in directory_path.iterdir():
        try:
            if item.is_file():
                item.unlink()
                deleted_count += 1
                print(f"  ✓ Deleted file: {item.name}")
            elif item.is_dir():
                file_count = sum(1 for _ in item.rglob("*") if _.is_file())
                shutil.rmtree(item)
                deleted_count += 1
                print(f"  ✓ Deleted directory: {item.name}/ ({file_count} files)")
        except Exception as e:
            print(f"  ✗ Failed to delete {item.name}: {e}")

    return deleted_count


def initialize(output_dir, skip_analyzer=False):
    """
    Initialize RAS API by clearing client-side output directories.

    Args:
        output_dir: Path to ras_demo_output directory
        skip_analyzer: If True, skip clearing Analyzer_output_files

    Returns:
        Total number of items deleted
    """
    print("\n" + "=" * 60)
    print("RAS API Initialization - Clearing Client Output Directories")
    print("=" * 60 + "\n")

    total_deleted = 0

    # --- cper_storage ---
    cper_storage = output_dir / "cper_storage"
    print(f"Clearing CPER storage: {cper_storage}")
    deleted = clear_directory(cper_storage, "cper_storage")
    total_deleted += deleted
    if deleted == 0:
        print(f"  ⓘ Directory is already empty")
    # Ensure the directory still exists after clearing
    cper_storage.mkdir(parents=True, exist_ok=True)
    print()

    # --- cpad_storage ---
    cpad_storage = output_dir / "cpad_storage"
    print(f"Clearing CPAD storage: {cpad_storage}")
    deleted = clear_directory(cpad_storage, "cpad_storage")
    total_deleted += deleted
    if deleted == 0:
        print(f"  ⓘ Directory is already empty")
    cpad_storage.mkdir(parents=True, exist_ok=True)
    print()

    # --- Analyzer output (includes error_history.json) ---
    if not skip_analyzer:
        analyzer_dir = output_dir / "Analyzer_output_files"
        print(f"Clearing Analyzer output: {analyzer_dir}")
        deleted = clear_directory(analyzer_dir, "Analyzer_output_files")
        total_deleted += deleted
        if deleted == 0:
            print(f"  ⓘ Directory is already empty")
        analyzer_dir.mkdir(parents=True, exist_ok=True)
        print()
    else:
        print(f"Skipping Analyzer output (--no-analyzer)\n")

    print("=" * 60)
    print(f"Summary: {total_deleted} total items deleted")
    print("=" * 60 + "\n")

    return total_deleted


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Initialize RAS API by clearing client-side CPER/CPAD storage directories",
        epilog="Example: python scripts/initializeRasApi.py --all",
    )
    parser.add_argument(
        "--output-dir",
        default="ras_demo_output",
        help="Path to output directory (default: ras_demo_output)",
    )
    parser.add_argument(
        "--no-analyzer",
        action="store_true",
        help="Skip clearing Analyzer_output_files (error_history.json etc.)",
    )

    args = parser.parse_args()

    # Resolve output dir relative to project root
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    # Ensure base output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    skip_analyzer = args.no_analyzer

    total_deleted = initialize(output_dir, skip_analyzer=skip_analyzer)

    if total_deleted > 0:
        print("✓ RAS API initialization complete - directories cleared")
    else:
        print("✓ RAS API initialization complete - directories were already empty")

    sys.exit(0)


if __name__ == "__main__":
    main()
