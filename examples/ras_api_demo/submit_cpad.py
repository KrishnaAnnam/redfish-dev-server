#!/usr/bin/env python3
"""
Binary CPAD Submission Module
==============================

Reads binary CPAD files, validates the CPAD signature, extracts platformID,
base64-encodes the binary, and submits as JSON to the BMC Redfish endpoint.

Transport format:
    POST /redfish/v1/Managers/{id}/Oem/RasProto/RASService/Actions/RasProto.SubmitCPAD
    Content-Type: application/json
    {"CPADData": "<base64>", "EncodingType": "Base64"}

Usage (standalone):
    python examples/ras_api_demo/submit_cpad.py cpad_storage/memErrorSpoof.cpad
    python examples/ras_api_demo/submit_cpad.py cpad_storage/spprSpoof.cpad --server http://localhost:8001

Usage (from orchestrator):
    from submit_cpad import CPADSubmitter
    submitter = CPADSubmitter(base_url=url, manager_id="System")
    submitter.submit(path, verbose_steps=True)
"""

import sys
import struct
import base64
import time
import argparse
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

# CPAD Header Structure Constants
CPAD_SIGNATURE_START = 0x44415043  # "CPAD" in little-endian
CPAD_SIGNATURE_END = 0xFFFFFFFF
CPAD_HEADER_MIN_SIZE = 48


# ─── CPAD Binary Parsing ───────────────────────────────────────────────

def parse_guid(data: bytes) -> str:
    """Parse a GUID from 16 bytes of binary data (mixed-endian format)."""
    if len(data) != 16:
        raise ValueError(f"GUID must be 16 bytes, got {len(data)}")
    data1 = struct.unpack('<I', data[0:4])[0]
    data2 = struct.unpack('<H', data[4:6])[0]
    data3 = struct.unpack('<H', data[6:8])[0]
    data4 = data[8:16]
    return (f"{data1:08x}-{data2:04x}-{data3:04x}-"
            f"{data4[0]:02x}{data4[1]:02x}-"
            f"{data4[2]:02x}{data4[3]:02x}{data4[4]:02x}"
            f"{data4[5]:02x}{data4[6]:02x}{data4[7]:02x}")


def read_binary_cpad(file_path, verbose=False):
    """Read a binary CPAD file, validate signature, extract platformID/partitionID.

    Args:
        file_path: Path to the binary CPAD file.
        verbose:   Enable verbose output.

    Returns:
        dict with 'platformID', 'partitionID', and 'rawData'.

    Raises:
        ValueError: If the file is not a valid CPAD file.
    """
    with open(file_path, 'rb') as f:
        raw_data = f.read()

    if len(raw_data) < CPAD_HEADER_MIN_SIZE:
        raise ValueError(f"File too small to be a valid CPAD file (size: {len(raw_data)} bytes)")

    # Validate CPAD Signature
    offset = 0
    signature_start = struct.unpack('<I', raw_data[offset:offset + 4])[0]
    if signature_start != CPAD_SIGNATURE_START:
        sig_bytes = raw_data[0:4]
        sig_ascii = sig_bytes.decode('ascii', errors='replace')
        raise ValueError(
            f"Invalid CPAD file: Header does not start with 'CPAD' signature. "
            f"Got: 0x{signature_start:08X} ('{sig_ascii}')")

    if verbose:
        print(f"  ✓ Valid CPAD signature found at file start")

    offset += 4

    # Revision (2 bytes: minor, major)
    offset += 2

    # SignatureEnd (4 bytes)
    signature_end = struct.unpack('<I', raw_data[offset:offset + 4])[0]
    offset += 4

    if signature_end != CPAD_SIGNATURE_END:
        raise ValueError(
            f"Invalid CPAD signature end: expected 0x{CPAD_SIGNATURE_END:08X}, "
            f"got 0x{signature_end:08X}")

    # Skip to PlatformID:
    #   SectionCount(2) + Urgency(1) + Confidence(1) + Reserved(2)
    #   + ValidationBits(4) + RecordLength(4) + Timestamp(8) = 22 bytes
    offset += 2 + 1 + 1 + 2 + 4 + 4 + 8

    # PlatformID (16 bytes GUID)
    platform_id = parse_guid(raw_data[offset:offset + 16])
    offset += 16

    # PartitionID (16 bytes GUID)
    partition_id = parse_guid(raw_data[offset:offset + 16])

    if verbose:
        print(f"  ✓ Platform ID: {platform_id}")
        print(f"  ✓ Partition ID: {partition_id}")
        print(f"    File size: {len(raw_data)} bytes")

    return {
        'platformID': platform_id,
        'partitionID': partition_id,
        'rawData': raw_data,
    }


# ─── Submitter Class ───────────────────────────────────────────────────

class CPADSubmitter:
    """Submits binary CPAD files to a BMC via Redfish (base64 + JSON).

    Standalone module — only depends on requests.  No analysis or policy logic.
    """

    def __init__(self, *, base_url, manager_id="System", platform_bmc_map=None):
        """Initialize the CPAD submitter.

        Args:
            base_url:         Default BMC base URL (e.g. "http://localhost:8000").
            manager_id:       Redfish Manager ID.
            platform_bmc_map: Optional dict mapping platformID → BMC URL for
                              multi-BMC environments.
        """
        self.base_url = base_url
        self.manager_id = manager_id
        self.platform_bmc_map = platform_bmc_map or {}

    def submit(self, cpad_file_path, *, verbose_steps=True, source_label=None):
        """Submit a binary CPAD file to the BMC.

        Reads the file, validates the CPAD signature, base64-encodes,
        and POSTs as JSON to the SubmitCPAD action endpoint.

        Args:
            cpad_file_path: Path to the binary .cpad file.
            verbose_steps:  Show detailed step-by-step output.
            source_label:   Description of the CPAD source for Step 1 output.

        Returns:
            bool: True if the BMC accepted the CPAD, False otherwise.
        """
        try:
            cpad_file_path = Path(cpad_file_path)

            if verbose_steps:
                label = source_label or "Loading CPAD file"
                print(f"\n   Step 1: {label}")
                print(f"           File: {cpad_file_path.name}")

            # Read and validate binary CPAD
            cpad_info = read_binary_cpad(str(cpad_file_path), verbose=False)

            platform_id = cpad_info['platformID']
            partition_id = cpad_info['partitionID']

            if verbose_steps:
                print(f"           ✓ Valid CPAD signature verified")
                print(f"           ✓ File size: {len(cpad_info['rawData'])} bytes")

                print(f"\n   Step 2: Parsing CPAD header")
                print(f"           Platform ID:  {platform_id}")
                print(f"           Partition ID: {partition_id}")

            # Determine target BMC URL based on platformID
            if verbose_steps:
                print(f"\n   Step 3: Performing lookup for target BMC URL on Platform ID {platform_id}")

            if self.platform_bmc_map and platform_id in self.platform_bmc_map:
                target_url = self.platform_bmc_map[platform_id].rstrip('/')
                if verbose_steps:
                    print(f"           ✓ Found mapping in platform-BMC map")
            else:
                target_url = self.base_url

            if verbose_steps:
                print(f"           Target BMC: {target_url}")

            # Base64-encode binary CPAD and wrap in JSON
            raw_data = cpad_info['rawData']
            b64_cpad = base64.b64encode(raw_data).decode('ascii')
            json_payload = {
                'CPADData': b64_cpad,
                'EncodingType': 'Base64',
            }

            # Submit CPAD to BMC as JSON
            endpoint = (f"{target_url}/redfish/v1/Managers/{self.manager_id}"
                        f"/Oem/RasProto/RASService/Actions/RasProto.SubmitCPAD")

            if verbose_steps:
                print(f"\n   Step 4: Base64 encoding binary CPAD for JSON transport")
                print(f"           Binary size: {len(raw_data)} bytes → Base64 size: {len(b64_cpad)} bytes")
                print(f"           Submitting JSON payload to BMC")
                print(f"           Redfish URI Endpoint: {endpoint}")
                print(f"           Method: POST")
                print(f"           Content-Type: application/json")
            else:
                print(f"\n   📤 Submitting: {cpad_file_path.name}")

            response = requests.post(endpoint, json=json_payload, timeout=30)

            if verbose_steps:
                print(f"\n   Step 5: Receiving response from BMC")

            if response.status_code in [200, 201, 202]:
                if verbose_steps:
                    print(f"           ✓ BMC accepted the CPAD (Response status: {response.status_code})")
                    print()
                    print(f"   ┌─────────────────────────────────────────────────────────────┐")
                    print(f"   │  Look at the SERVER pane for processing details             │")
                    print(f"   │  (CPAD decode, validation, CPER creation)                   │")
                    print(f"   │                                                             │")
                    print(f"   │  Look at the LISTENER pane to receive notifications,        │")
                    print(f"   │  download and store CPERs                                   │")
                    print(f"   └─────────────────────────────────────────────────────────────┘")

                    time.sleep(2)

                    print(f"\n   Step 6: Saving the CPAD to the infrastructure cloud database")
                    print(f"           ✓ CPAD is stored in {cpad_file_path.parent}")
                else:
                    print(f"      ✓ Accepted by BMC")
                return True
            else:
                error_msg = response.text if response.text else "Unknown error"
                if verbose_steps:
                    print(f"           ✗ BMC rejected the CPAD: {error_msg}")
                else:
                    print(f"      ✗ Failed: {error_msg}")
                return False

        except ValueError as e:
            print(f"\n   ✗ Invalid CPAD file: {e}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"\n   ✗ Cannot connect to server at {self.base_url}")
            return False
        except requests.exceptions.Timeout:
            print(f"\n   ✗ Request timeout")
            return False
        except Exception as e:
            print(f"\n   ✗ Error: {e}")
            return False

    def submit_sppr_cpads(self, analyzer_output_dir):
        """Submit analyzer-generated SPPR CPAD file(s).

        Looks in the given directory for *_sppr_cpad.cpad (binary) or
        *_sppr_cpad.json (fallback) files.

        Args:
            analyzer_output_dir: Path to the Analyzer_output_files directory.

        Returns:
            int: Number of successfully submitted files.
        """
        analyzer_output_dir = Path(analyzer_output_dir)

        print("\n" + "=" * 80)
        print("\t\t\t\tSUBMIT SPPR CPAD")
        print("=" * 80)

        if not analyzer_output_dir.exists():
            print(f"\n⚠️  Analyzer output directory not found: {analyzer_output_dir}")
            return 0

        # Prefer binary SPPR CPAD files, fall back to JSON
        sppr_binary_files = list(analyzer_output_dir.glob("*_sppr_cpad.cpad"))
        sppr_json_files = list(analyzer_output_dir.glob("*_sppr_cpad.json"))

        if sppr_binary_files:
            sppr_files = sppr_binary_files
            print(f"   Found {len(sppr_files)} binary SPPR CPAD file(s)")
        elif sppr_json_files:
            sppr_files = sppr_json_files
            print(f"   Found {len(sppr_files)} JSON SPPR CPAD file(s) (binary not available)")
        else:
            print(f"\n⚠️  No SPPR CPAD files found in {analyzer_output_dir}")
            print(f"   (SPPR CPADs are only created for CMC notifications on Platform Memory 2 errors)")
            return 0

        submitted_count = 0

        for idx, sppr_file in enumerate(sppr_files, 1):
            print(f"\n{'─' * 80}")
            print(f"📋 SPPR CPAD {idx}/{len(sppr_files)}: {sppr_file.name}")
            print(f"{'─' * 80}")

            print(f"\n🚀 Initiating SPPR CPAD submission...")

            if sppr_file.suffix.lower() != '.cpad':
                print(f"   Note: Using JSON format — binary CPAD generation not yet available")

            success = self.submit(
                sppr_file, verbose_steps=True,
                source_label="Loading SPPR repair CPAD file from Analyzer")

            if success:
                submitted_count += 1

        if submitted_count > 0:
            print(f"\n✅ Successfully submitted {submitted_count} SPPR CPAD file(s)")
        else:
            print(f"\n⚠️  No SPPR CPAD files were submitted successfully")

        return submitted_count


# ─── CLI Entry Point ────────────────────────────────────────────────────

def main():
    """Command-line interface for standalone CPAD submission."""
    parser = argparse.ArgumentParser(
        description='Submit binary CPAD file to BMC via Redfish (base64 + JSON)',
        epilog='Examples:\n'
               '  python examples/ras_api_demo/submit_cpad.py cpad_storage/memErrorSpoof.cpad\n'
               '  python examples/ras_api_demo/submit_cpad.py cpad_storage/spprSpoof.cpad --server http://localhost:8001\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('cpad_file', help='Path to the binary CPAD file (.cpad)')
    parser.add_argument('--server', default='http://localhost:8000',
                        help='BMC server URL (default: http://localhost:8000)')
    parser.add_argument('--manager-id', default='System',
                        help='Redfish Manager ID (default: System)')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    submitter = CPADSubmitter(base_url=args.server, manager_id=args.manager_id)
    success = submitter.submit(args.cpad_file, verbose_steps=args.verbose)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
