#!/usr/bin/env python3
"""
CPER / CPAD binary decoding via cperlib
========================================

Generic, analyzer-agnostic wrapper around cperlib's ``cper-convert`` and
``cpad-convert`` tools.  This module knows nothing about any particular chip
vendor's analysis logic — it only converts between binary and JSON.

Consumers:
- The Analysis Orchestrator uses it to decode a CPER's header (CreatorID,
  timestamp, Platform/Partition IDs) for routing.
- Analyzer plugins use it to decode CPERs and to emit binary CPADs.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


# Resolve paths relative to project root (Demos/RasApi/ → project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class CperDecoder:
    """Decode binary CPER/CPAD files using cperlib's command-line tools."""

    def __init__(self, verbose: bool = False):
        """Initialize the decoder.

        Args:
            verbose: Enable verbose diagnostics.
        """
        self.verbose = verbose

    # ─── Tool Location ──────────────────────────────────────────────────

    def _locate_cper_convert(self):
        """Locate the cper-convert tool in the project's libcper build directory.

        Returns:
            tuple: (path_to_cper_convert, build_dir) or (None, None)
        """
        plugin_dir = PROJECT_ROOT / 'src' / 'plugins' / 'ras'
        build_dir = plugin_dir / 'libcper' / 'build'
        cper_convert = build_dir / 'cper-convert'

        if cper_convert.exists():
            return str(cper_convert), str(build_dir)

        return None, None

    def _locate_cpad_convert(self):
        """Locate the cpad-convert tool in the project's libcper build directory.

        Returns:
            tuple: (path_to_cpad_convert, build_dir) or (None, None)
        """
        plugin_dir = PROJECT_ROOT / 'src' / 'plugins' / 'ras'
        build_dir = plugin_dir / 'libcper' / 'build'
        cpad_convert = build_dir / 'cpad-convert'

        if cpad_convert.exists():
            return str(cpad_convert), str(build_dir)

        return None, None

    # ─── Conversion ─────────────────────────────────────────────────────

    def _convert_json_to_binary_cpad(self, json_path: str, output_path: str) -> Optional[str]:
        """Convert CPAD JSON to binary CPAD format using cperlib's cpad-convert tool.

        Args:
            json_path: Path to the CPAD JSON file
            output_path: Path for the output binary .cpad file

        Returns:
            str: Path to the binary CPAD file, or None if conversion failed
        """
        cpad_convert, build_dir = self._locate_cpad_convert()
        if not cpad_convert:
            print(f"   ✗ cpad-convert tool not found at src/plugins/ras/libcper/build/")
            return None

        try:
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = build_dir + ':' + env.get('LD_LIBRARY_PATH', '')

            # Resolve to absolute paths since cwd is the build directory
            abs_json_path = str(Path(json_path).resolve())
            abs_output_path = str(Path(output_path).resolve())
            cmd = [cpad_convert, 'to-cpad', abs_json_path, '--out', abs_output_path, '--no-validate']

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=build_dir,
                env=env
            )
            stdout, stderr = proc.communicate(timeout=10)

            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                print(f"   ✗ cpad-convert failed: {err_msg}")
                return None

            if os.path.exists(output_path):
                return output_path

            print(f"   ✗ Binary CPAD file not created: {output_path}")
            return None

        except subprocess.TimeoutExpired:
            print(f"   ✗ cpad-convert timed out after 10 seconds")
            return None
        except Exception as e:
            print(f"   ✗ Error converting to binary CPAD: {e}")
            return None

    def _convert_binary_cper_to_json(self, binary_path: str) -> Optional[Dict[str, Any]]:
        """Convert a binary .cper file to JSON using cperlib's cper-convert tool.

        Args:
            binary_path: Path to the binary .cper file

        Returns:
            dict: Parsed CPER JSON data, or None if conversion failed
        """
        cper_convert, build_dir = self._locate_cper_convert()
        if not cper_convert:
            print(f"   ✗ cper-convert tool not found at src/plugins/ras/libcper/build/")
            return None

        try:
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = build_dir + ':' + env.get('LD_LIBRARY_PATH', '')

            # Resolve to absolute path since cwd is the build directory
            abs_binary_path = str(Path(binary_path).resolve())
            cmd = [cper_convert, 'to-json', abs_binary_path]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=build_dir,
                env=env
            )
            stdout, stderr = proc.communicate(timeout=10)

            if proc.returncode != 0:
                err_msg = stderr.decode('utf-8', errors='replace').strip()
                print(f"   ✗ cper-convert failed: {err_msg}")
                return None

            json_text = stdout.decode('utf-8', errors='replace')
            cper_data = json.loads(json_text)
            return cper_data

        except subprocess.TimeoutExpired:
            print(f"   ✗ cper-convert timed out after 10 seconds")
            return None
        except json.JSONDecodeError as e:
            print(f"   ✗ cper-convert output is not valid JSON: {e}")
            return None
        except Exception as e:
            print(f"   ✗ Error converting binary CPER: {e}")
            return None

    # ─── CPER Data Extraction ───────────────────────────────────────────

    def extract_cper_data(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Extract full CPER data from a binary .cper file.

        Uses cperlib's cper-convert tool to decode binary CPER to JSON.

        Args:
            file_path: Path to a binary .cper file

        Returns:
            dict: Full CPER data (with header, sectionDescriptors, sections) or None
        """
        cper_data = self._convert_binary_cper_to_json(file_path)
        if cper_data and 'header' in cper_data:
            return cper_data
        if self.verbose:
            print(f"   ⚠️  cper-convert did not produce valid CPER JSON for {file_path}")
        return None
