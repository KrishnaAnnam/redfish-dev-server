#!/usr/bin/env python3
"""
Reset Server - Reset BMC/Redfish server-side RAS state

Deletes all CPER log entries from the RAS LogService on the server file system,
resets the Entries collection index, and optionally cleans up the temporary CPER
directories the server creates during binary-CPER conversion.

This script only touches BMC/Redfish server-side state. Client-side demo output
(cper_storage/, cpad_storage/, analyzer output) is owned by init_error_pipeline.py.

Usage:
    python scripts/resetServer.py
    python scripts/resetServer.py --mockdir mockups/public-rackmount1
    python scripts/resetServer.py --mockdir mockups/ras_gen1 --manager System
    python scripts/resetServer.py --clean-temp
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
    entries_uri = f"/redfish/v1/Managers/{manager_id}/LogServices/CPER/Entries"
    
    empty_collection = {
        "@odata.type": "#LogEntryCollection.LogEntryCollection",
        "@odata.id": entries_uri,
        "Name": "CPER Log Entries",
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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Reset RAS LogService by deleting all log entries and CPER files from the server file system',
        epilog='Example: python scripts/resetServer.py --mockdir mockups/public-rackmount1'
    )
    parser.add_argument(
        '--mockdir',
        default='mockups/ras_gen1',
        help='Path to the mockup directory (default: mockups/ras_gen1)'
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
    
    args = parser.parse_args()
    
    # Resolve paths relative to the project root (examples/ras_api_demo/ -> Demos/ -> project root)
    project_root = Path(__file__).resolve().parent.parent.parent
    
    mockdir = Path(args.mockdir)
    if not mockdir.is_absolute():
        mockdir = project_root / mockdir
    
    if not mockdir.exists():
        print(f"Error: Mockup directory not found: {mockdir}")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("BMC/Redfish Server Reset")
    print("=" * 60)
    
    # Step 1: Reset RAS LogService Entries
    entries_path = mockdir / "redfish" / "v1" / "Managers" / args.manager / "LogServices" / "CPER" / "Entries"
    
    print(f"\n📋 Step 1: Resetting RAS LogService Entries")
    print(f"   Path: {entries_path}")
    entry_count = reset_log_entries(entries_path, args.manager)
    
    # Step 2: Clean temp directories (optional)
    temp_count = 0
    if args.clean_temp:
        print(f"\n🗑️  Step 2: Cleaning temporary CPER directories")
        temp_count = clean_temp_cper_dirs()
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Log entries deleted:  {entry_count}")
    if args.clean_temp:
        print(f"  Temp dirs cleaned:    {temp_count}")
    
    total = entry_count + temp_count
    if total > 0:
        print(f"\n✅ BMC/Redfish server reset complete - {total} item(s) cleaned")
    else:
        print(f"\n✅ BMC/Redfish server was already clean - nothing to reset")
    
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
