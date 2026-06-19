#!/usr/bin/env python3
"""
CPER Collection Module
=======================

Collects CPER (Common Platform Error Record) files from the BMC's
RAS LogService, downloads binary attachments, and clears the log.

Usage (standalone):
    python examples/ras_api_demo/collect_cpers.py
    python examples/ras_api_demo/collect_cpers.py --server http://localhost:8001 --output-dir ./cpers

Usage (from orchestrator):
    from collect_cpers import CPERCollector
    collector = CPERCollector(session=s, base_url=url, manager_id="System",
                              platform_id=pid, partition_id=ptid,
                              cper_storage_dir=storage_path)
    collector.collect()
"""

import sys
import json
import time
import argparse
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)


class CPERCollector:
    """Collects CPER files from the BMC RAS LogService.

    Downloads binary CPER attachments from each LogEntry, saves them under
    cper_storage/{platform_id}/{partition_id}/, and clears the server log.
    """

    def __init__(self, *, session=None, base_url, manager_id="System",
                 platform_id, partition_id, cper_storage_dir):
        """Initialize the CPER collector.

        Args:
            session:          requests.Session (creates one if not provided).
            base_url:         BMC base URL, e.g. "http://localhost:8000".
            manager_id:       Redfish Manager ID.
            platform_id:      Platform GUID string.
            partition_id:     Partition GUID string.
            cper_storage_dir: Root directory for storing collected CPERs.
        """
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip('/')
        self.manager_id = manager_id
        self.platform_id = platform_id
        self.partition_id = partition_id
        self.cper_storage_dir = Path(cper_storage_dir)

    def collect(self):
        """Collect CPERs from the RAS LogService.

        1. Query the RAS LogService Entries collection.
        2. Download binary CPER from each entry's Attachment endpoint.
        3. Clear the server log after successful download.

        Returns:
            int: Number of CPER files downloaded.
        """
        print("\n" + "=" * 80)
        print("\t\t\t\tCOLLECTING CPERs")
        print("=" * 80)

        try:
            # Step 1: Query the RAS LogService Entries collection
            log_entries_url = f"/redfish/v1/Managers/{self.manager_id}/LogServices/RAS/Entries"

            print(f"\n   Step 1: Querying RAS LogService Entries")
            print(f"📡 GET {self.base_url}{log_entries_url}")

            response = self.session.get(f"{self.base_url}{log_entries_url}")

            if response.status_code != 200:
                print(f"   ✗ Could not access RAS LogService Entries (Status: {response.status_code})")
                return 0

            entries_collection = response.json()
            members = entries_collection.get('Members', [])
            member_count = entries_collection.get('Members@odata.count', len(members))

            # Step 2: Report number of entries found
            print(f"\n   Step 2: Checking entry count")

            if member_count == 0 or not members:
                print(f"   ➜ No CPER entries found in RAS LogService")
                return 0

            print(f"   ➜ Found {member_count} entr{'y' if member_count == 1 else 'ies'} in RAS LogService\n")

            # Step 3: Download CPERs
            print(f"   Step 3: Downloading CPERs")
            downloaded_count = 0

            storage_path = self.cper_storage_dir / self.platform_id / self.partition_id
            storage_path.mkdir(parents=True, exist_ok=True)

            for idx, member in enumerate(members, 1):
                entry_uri = member.get('@odata.id', '')
                if not entry_uri:
                    continue

                # GET each individual entry (metadata)
                print(f"\n   📡 GET {self.base_url}{entry_uri}")
                entry_response = self.session.get(f"{self.base_url}{entry_uri}")
                if entry_response.status_code != 200:
                    print(f"      ✗ Failed to retrieve entry (Status: {entry_response.status_code})")
                    continue

                entry_data = entry_response.json()

                # Extract entry details
                entry_id = entry_data.get('Id', f'entry_{idx}')
                severity = entry_data.get('Severity', 'OK')
                message = entry_data.get('Message', 'CPER Entry')
                created = entry_data.get('Created', 'Unknown')
                entry_type = entry_data.get('EntryType', 'N/A')
                oem_format = entry_data.get('OemRecordFormat', 'N/A')

                # Display entry details
                print(f"      Entry #{idx}:")
                print(f"         Id: {entry_id}")
                print(f"         Severity: {severity}")
                print(f"         Message: {message}")
                print(f"         Created: {created}")
                print(f"         EntryType: {entry_type}")
                print(f"         OemRecordFormat: {oem_format}")

                # Download binary CPER from Attachment endpoint
                attachment_url = f"{self.base_url}{entry_uri}/Attachment"
                att_response = self.session.get(attachment_url)

                if att_response.status_code == 200:
                    content_type = att_response.headers.get('Content-Type', '')

                    if 'octet-stream' in content_type:
                        cper_filename = f"cper_{entry_id}_{int(time.time())}.cper"
                    else:
                        cper_filename = f"cper_{entry_id}_{int(time.time())}.json"

                    cper_file = storage_path / cper_filename
                    with open(cper_file, 'wb') as f:
                        f.write(att_response.content)
                else:
                    # No attachment available — save entry metadata as fallback
                    cper_filename = f"cper_{entry_id}_{int(time.time())}.json"
                    cper_file = storage_path / cper_filename
                    with open(cper_file, 'w') as f:
                        json.dump(entry_data, f, indent=2)

                downloaded_count += 1

                print(f"\n      📥 Downloaded: {cper_filename}")
                print(f"         Size: {cper_file.stat().st_size} bytes")

            # Step 4: Clear the LogService
            if downloaded_count > 0:
                print(f"\n   Step 4: Clearing RAS LogService")
                clear_url = (f"{self.base_url}/redfish/v1/Managers/{self.manager_id}"
                             f"/LogServices/RAS/Actions/LogService.ClearLog")
                print(f"   🗑️  POST {clear_url}")
                clear_response = self.session.post(clear_url, json={})
                if clear_response.status_code in [200, 204]:
                    print(f"      ✓ Server log cleared ({downloaded_count} "
                          f"entr{'y' if downloaded_count == 1 else 'ies'} removed)")
                else:
                    print(f"      ⚠️  Could not clear server log (Status: {clear_response.status_code})")

            # Summary
            if downloaded_count > 0:
                print(f"\n   ✅ {downloaded_count} CPER file(s) collected")
                print(f"      📂 {storage_path}")
            else:
                print(f"\n⚠️  No CPER files were downloaded")

            return downloaded_count

        except Exception as e:
            logger.error(f"Error collecting CPERs: {e}")
            print(f"\n❌ Error: {e}")
            return 0


# ─── CLI Entry Point ────────────────────────────────────────────────────

def main():
    """Command-line interface for standalone CPER collection."""
    parser = argparse.ArgumentParser(
        description='Collect CPER files from BMC RAS LogService',
        epilog='Examples:\n'
               '  python examples/ras_api_demo/collect_cpers.py\n'
               '  python examples/ras_api_demo/collect_cpers.py --server http://localhost:8001\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--server', default='http://localhost:8000',
                        help='BMC server URL (default: http://localhost:8000)')
    parser.add_argument('--manager-id', default='System',
                        help='Redfish Manager ID (default: System)')
    parser.add_argument('--platform-id',
                        default='990f8820-bd4d-5064-58cc-961a053dea79',
                        help='Platform GUID')
    parser.add_argument('--partition-id',
                        default='22222222-3333-4444-5555-666666666666',
                        help='Partition GUID')
    parser.add_argument('--output-dir',
                        help='Output directory for collected CPERs (default: ras_demo_output/cper_storage)')

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    default_storage = script_dir / "ras_demo_output" / "cper_storage"
    storage_dir = Path(args.output_dir) if args.output_dir else default_storage

    collector = CPERCollector(
        base_url=args.server,
        manager_id=args.manager_id,
        platform_id=args.platform_id,
        partition_id=args.partition_id,
        cper_storage_dir=str(storage_dir),
    )

    count = collector.collect()
    print(f"\nCollected {count} CPER file(s)")
    sys.exit(0 if count > 0 else 1)


if __name__ == "__main__":
    main()
