#!/usr/bin/env python3
"""
Reset Server - Clean up RAS LogService entries and CPER files

Deletes all CPER log entries from the RAS LogService on the server file system,
resets the Entries collection index, and optionally cleans up temp files and
client-side output directories.

Usage:
    python scripts/resetServer.py
    python scripts/resetServer.py --mockdir mockups/public-rackmount1
    python scripts/resetServer.py --mockdir mockups/ras_gen10 --manager System
    python scripts/resetServer.py --clean-temp --clean-output
"""

import os
import sys
import json
import shutil
import argparse
import tempfile
import glob
from pathlib import Path


def reset_log_entries(entries_path, manager_id):
    """
    Reset the RAS LogService Entries by removing all log entry directories
    and updating the index.json to show an empty collection.
    
    Args:
        entries_path: Path to the Entries directory
        manager_id: Manager ID for display
    
    Returns:
        Number of entries deleted
    """
    if not entries_path.exists():
        print(f"  ⓘ LogService Entries directory not found at {entries_path}")
        return 0
    
    deleted_count = 0
    
    # Find all subdirectories (each is a log entry)
    for item in sorted(entries_path.iterdir()):
        if item.is_dir() and item.name != "__pycache__":
            try:
                shutil.rmtree(item)
                deleted_count += 1
                print(f"  ✓ Deleted entry: {item.name}")
            except Exception as e:
                print(f"  ✗ Failed to delete {item.name}: {e}")
    
    # Update or create the index.json to show empty collection
    index_path = entries_path / "index.json"
    entries_uri = f"/redfish/v1/Managers/{manager_id}/LogServices/RAS/Entries"
    
    empty_collection = {
        "@odata.type": "#LogEntryCollection.LogEntryCollection",
        "@odata.id": entries_uri,
        "Name": "RAS Log Entries",
        "Members@odata.count": 0,
        "Members": []
    }
    
    try:
        with open(index_path, 'w') as f:
            json.dump(empty_collection, f, indent=2)
        print(f"  ✓ Updated Entries index.json (empty collection)")
    except Exception as e:
        print(f"  ✗ Failed to update index.json: {e}")
    
    return deleted_count


def clean_temp_cper_dirs():
    """
    Clean up temporary CPER directories created by the binary CPER conversion.
    These are created in the system temp directory with prefix 'ras_cper_'.
    
    Returns:
        Number of temp directories cleaned
    """
    temp_dir = tempfile.gettempdir()
    pattern = os.path.join(temp_dir, "ras_cper_*")
    temp_dirs = glob.glob(pattern)
    
    if not temp_dirs:
        print(f"  ⓘ No temporary CPER directories found")
        return 0
    
    cleaned_count = 0
    for d in sorted(temp_dirs):
        try:
            shutil.rmtree(d)
            cleaned_count += 1
            print(f"  ✓ Deleted temp dir: {os.path.basename(d)}")
        except Exception as e:
            print(f"  ✗ Failed to delete {os.path.basename(d)}: {e}")
    
    return cleaned_count


def clean_output_dir(output_dir):
    """
    Clean up the client-side demo output directory (ras_demo_output/).
    
    Args:
        output_dir: Path to the output directory
    
    Returns:
        Number of files/directories removed
    """
    if not output_dir.exists():
        print(f"  ⓘ Output directory not found: {output_dir}")
        return 0
    
    removed_count = 0
    
    # Clean cper_storage
    cper_storage = output_dir / "cper_storage"
    if cper_storage.exists():
        try:
            file_count = sum(1 for _ in cper_storage.rglob("*") if _.is_file())
            shutil.rmtree(cper_storage)
            cper_storage.mkdir(parents=True, exist_ok=True)
            removed_count += file_count
            print(f"  ✓ Cleared cper_storage/ ({file_count} files)")
        except Exception as e:
            print(f"  ✗ Failed to clear cper_storage/: {e}")
    
    # Clean cpad_storage
    cpad_storage = output_dir / "cpad_storage"
    if cpad_storage.exists():
        try:
            file_count = sum(1 for _ in cpad_storage.rglob("*") if _.is_file())
            shutil.rmtree(cpad_storage)
            cpad_storage.mkdir(parents=True, exist_ok=True)
            removed_count += file_count
            print(f"  ✓ Cleared cpad_storage/ ({file_count} files)")
        except Exception as e:
            print(f"  ✗ Failed to clear cpad_storage/: {e}")
    
    return removed_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Reset RAS LogService by deleting all log entries and CPER files from the server file system',
        epilog='Example: python scripts/resetServer.py --mockdir mockups/public-rackmount1'
    )
    parser.add_argument(
        '--mockdir',
        default='mockups/ras_gen10',
        help='Path to the mockup directory (default: mockups/ras_gen10)'
    )
    parser.add_argument(
        '--manager',
        default='System',
        help='Manager ID (default: System)'
    )
    parser.add_argument(
        '--clean-temp',
        action='store_true',
        help='Also clean up temporary CPER directories in system temp'
    )
    parser.add_argument(
        '--clean-output',
        action='store_true',
        help='Also clean up client-side ras_demo_output/ directory'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Clean everything: server entries, temp files, and output directory'
    )
    
    args = parser.parse_args()
    
    if args.all:
        args.clean_temp = True
        args.clean_output = True
    
    # Resolve paths relative to the project root (examples/ras_api_demo/ -> Demos/ -> project root)
    project_root = Path(__file__).resolve().parent.parent.parent
    
    mockdir = Path(args.mockdir)
    if not mockdir.is_absolute():
        mockdir = project_root / mockdir
    
    if not mockdir.exists():
        print(f"Error: Mockup directory not found: {mockdir}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("RAS Server Reset")
    print("=" * 60)
    
    # Step 1: Reset RAS LogService Entries
    entries_path = mockdir / "redfish" / "v1" / "Managers" / args.manager / "LogServices" / "RAS" / "Entries"
    
    print(f"\n📋 Step 1: Resetting RAS LogService Entries")
    print(f"   Path: {entries_path}")
    entry_count = reset_log_entries(entries_path, args.manager)
    
    # Step 2: Clean temp directories (optional)
    temp_count = 0
    if args.clean_temp:
        print(f"\n🗑️  Step 2: Cleaning temporary CPER directories")
        temp_count = clean_temp_cper_dirs()
    
    # Step 3: Clean output directory (optional)
    output_count = 0
    if args.clean_output:
        step_num = 3 if args.clean_temp else 2
        script_dir = Path(__file__).resolve().parent
        output_dir = script_dir / "ras_demo_output"
        print(f"\n🗑️  Step {step_num}: Cleaning client output directory")
        print(f"   Path: {output_dir}")
        output_count = clean_output_dir(output_dir)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Log entries deleted:  {entry_count}")
    if args.clean_temp:
        print(f"  Temp dirs cleaned:    {temp_count}")
    if args.clean_output:
        print(f"  Output files removed: {output_count}")
    
    total = entry_count + temp_count + output_count
    if total > 0:
        print(f"\n✅ Server reset complete - {total} item(s) cleaned")
    else:
        print(f"\n✅ Server was already clean - nothing to reset")
    
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
