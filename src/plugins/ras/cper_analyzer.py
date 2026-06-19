"""
CPER Analyzer

Analyzes CPER (Common Platform Error Record) files by converting them to JSON
format using the CPERgen cper-convert tool.

Extracted and adapted from RasApi-main/Analyzer.py
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import logging

from .models.cpad_types import CPERRecord

logger = logging.getLogger(__name__)


class CPERAnalyzer:
    """Analyzes CPER files by converting them to JSON format using cper-convert."""
    
    # Registry of Creator IDs to analyzer tool names
    ANALYZER_REGISTRY = {
        '11111111-2222-3333-4444-555555555555': 'Contoso CPER analyzer',
        # Add more creator IDs and their analyzers here
    }
    
    def __init__(self, verbose: bool = False):
        """
        Initialize CPER analyzer.
        
        Args:
            verbose: Enable verbose output
        """
        self.base_path = Path(__file__).parent
        self.output_dir = self.base_path / "analyzer_output"
        self.output_dir.mkdir(exist_ok=True)
        self.verbose = verbose
        
        # Template directory for SPPR and other templates
        self.template_dir = self.base_path / "templates"
        
        # Locate the cper-convert tool
        self.cper_convert_tool = None
        self.build_dir = None
        self._locate_cper_convert_tool()
    
    def _locate_cper_convert_tool(self):
        """Locate the cper-convert tool in the CPERgen build directory."""
        # Search paths in priority order
        plugin_dir = Path(__file__).parent
        possible_paths = [
            # 1. Our integrated libcper (highest priority)
            plugin_dir / "libcper" / "build" / "cper-convert",
            # 2. RasApi reference directory
            plugin_dir.parent.parent.parent / "references" / "RasApi-main" / "CPERgen" / "libcper" / "build" / "cper-convert",
            # 3. System-wide installation
            Path("/usr/local/bin/cper-convert"),
            Path("/usr/bin/cper-convert"),
            # 4. User home directory
            Path.home() / "CPERgen" / "libcper" / "build" / "cper-convert",
        ]
        
        # Detect if we're running inside WSL
        is_wsl = os.path.exists('/proc/version') and 'microsoft' in open('/proc/version').read().lower()
        
        # On Windows (not in WSL), cper-convert is a Linux binary accessed via WSL
        if sys.platform == 'win32' and not is_wsl:
            for path in possible_paths:
                if path.exists():
                    # Convert Windows path to WSL path
                    wsl_build_path = str(path).replace('\\', '/')
                    if len(wsl_build_path) > 1 and wsl_build_path[1] == ':':
                        drive = wsl_build_path[0].lower()
                        wsl_build_path = f"/mnt/{drive}{wsl_build_path[2:]}"
                    
                    wsl_cper_convert = f"{wsl_build_path}/cper-convert"
                    result = subprocess.run(
                        ["wsl", "test", "-f", wsl_cper_convert],
                        capture_output=True
                    )
                    if result.returncode == 0:
                        self.cper_convert_tool = str(path / "cper-convert")
                        self.build_dir = str(path)
                        if self.verbose:
                            logger.info(f"Found cper-convert at: {self.cper_convert_tool}")
                        return
        else:
            # On Linux/Mac or in WSL, look for the actual executable
            for path in possible_paths:
                if path.exists():
                    self.cper_convert_tool = str(path)
                    self.build_dir = str(path.parent)
                    if self.verbose:
                        logger.info(f"Found cper-convert at: {self.cper_convert_tool}")
                    return
        
        # If not found, log warning but don't fail - can use mock data
        logger.warning(
            "Could not locate cper-convert tool. CPER analysis will use mock data.\n"
            "To enable real CPER analysis, build the integrated libcper:\n"
            "  cd src/plugins/ras/libcper\n"
            "  meson setup build\n"
            "  ninja -C build\n"
            "\n"
            "For BMC integration, install system-wide:\n"
            "  sudo ninja -C build install"
        )
        self.cper_convert_tool = None
    
    def _windows_to_wsl_path(self, windows_path: str) -> str:
        """Convert a Windows path to WSL path format."""
        path_str = str(windows_path).replace('\\', '/')
        if len(path_str) > 1 and path_str[1] == ':':
            drive = path_str[0].lower()
            path_str = f"/mnt/{drive}{path_str[2:]}"
        return path_str
    
    def analyze_cper_file(self, cper_file_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a CPER file and convert to JSON.
        
        Args:
            cper_file_path: Path to the CPER file
            
        Returns:
            dict: CPER data in JSON format, or None if analysis failed
        """
        cper_path = Path(cper_file_path)
        
        if not cper_path.exists():
            logger.error(f"CPER file not found: {cper_path}")
            return None
        
        # If cper-convert is not available, return mock data
        if self.cper_convert_tool is None:
            logger.warning(f"Using mock CPER analysis for: {cper_path.name}")
            return self._create_mock_cper_json(cper_path)
        
        # Use cper-convert to analyze
        try:
            output_file = self.output_dir / f"{cper_path.stem}.json"
            
            # Detect platform
            is_wsl = os.path.exists('/proc/version') and 'microsoft' in open('/proc/version').read().lower()
            
            if sys.platform == 'win32' and not is_wsl:
                # Windows: use WSL
                wsl_input = self._windows_to_wsl_path(str(cper_path.absolute()))
                wsl_output = self._windows_to_wsl_path(str(output_file.absolute()))
                wsl_tool = self._windows_to_wsl_path(self.cper_convert_tool)
                
                cmd = ["wsl", wsl_tool, wsl_input, wsl_output]
            else:
                # Linux/Mac/WSL: direct execution
                cmd = [self.cper_convert_tool, str(cper_path.absolute()), str(output_file.absolute())]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.error(f"cper-convert failed: {result.stderr}")
                return None
            
            # Load the generated JSON
            with open(output_file, 'r') as f:
                cper_json = json.load(f)
            
            logger.info(f"Successfully analyzed CPER: {cper_path.name}")
            return cper_json
            
        except subprocess.TimeoutExpired:
            logger.error(f"cper-convert timeout for: {cper_path.name}")
            return None
        except Exception as e:
            logger.error(f"Error analyzing CPER {cper_path.name}: {e}")
            return None
    
    def _create_mock_cper_json(self, cper_path: Path) -> Dict[str, Any]:
        """
        Create mock CPER JSON data for testing when cper-convert is unavailable.
        
        Args:
            cper_path: Path to CPER file
            
        Returns:
            dict: Mock CPER data
        """
        return {
            "header": {
                "signatureStart": "CPER",
                "revision": {"major": 1, "minor": 0},
                "signatureEnd": 0xFFFFFFFF,
                "sectionCount": 1,
                "errorSeverity": {"name": "ERR_CORRECTED", "value": 0},
                "validationBits": {},
                "recordLength": 296,
                "timestamp": datetime.now().isoformat(),
                "timestampIsPrecise": True,
                "platformID": "990f8820-bd4d-5064-58cc-961a053dea79",
                "partitionID": "00000000-0000-0000-0000-000000000000",
                "creatorID": "11111111-2222-3333-4444-555555555555",
                "notificationType": {
                    "guid": "2dce8bb1-bdd7-450e-b9ad-9cf4ebd4f890",
                    "type": "Corrected Machine Check (CMC)"
                },
                "recordID": int(datetime.now().timestamp()),
                "flags": {},
                "persistenceInfo": 0
            },
            "sectionDescriptors": [
                {
                    "sectionOffset": 200,
                    "sectionLength": 96,
                    "revision": {"major": 1, "minor": 0},
                    "validationBits": {},
                    "flags": {},
                    "sectionType": {
                        "data": "61ec04fc-48e6-d813-25c9-8daa44750b12",
                        "type": "Platform Memory 2"
                    },
                    "fruID": "75824856-bd36-2cc8-61f4-39bb3276da2a",
                    "fruText": "DIMM A1",
                    "errorSeverity": {"name": "ERR_CORRECTED", "value": 0}
                }
            ],
            "sections": [
                {
                    "Memory2": {
                        "errorStatus": {
                            "errorType": {
                                "name": "ERR_MEM",
                                "value": 4,
                                "description": "Single correctable error"
                            }
                        },
                        "physicalAddress": 0x6942759454E18F7B,
                        "physicalAddressHex": "0x6942759454E18F7B"
                    }
                }
            ],
            "_mock": True,
            "_source_file": str(cper_path.name)
        }
    
    def analyze_multiple_cper_files(self, cper_files: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Analyze multiple CPER files.
        
        Args:
            cper_files: List of paths to CPER files
            
        Returns:
            dict: Mapping of filename to CPER JSON data
        """
        results = {}
        
        for cper_file in cper_files:
            cper_path = Path(cper_file)
            results[cper_path.name] = self.analyze_cper_file(cper_file)
        
        return results
    
    def get_cper_summary(self, cper_json: Dict[str, Any]) -> str:
        """
        Generate human-readable summary of CPER data.
        
        Args:
            cper_json: CPER data in JSON format
            
        Returns:
            str: Formatted summary
        """
        header = cper_json.get('header', {})
        sections = cper_json.get('sections', [])
        
        lines = [
            "CPER Record Summary:",
            f"  Record ID: {header.get('recordID', 'Unknown')}",
            f"  Timestamp: {header.get('timestamp', 'Unknown')}",
            f"  Severity: {header.get('errorSeverity', {}).get('name', 'Unknown')}",
            f"  Platform ID: {header.get('platformID', 'Unknown')}",
            f"  Creator ID: {header.get('creatorID', 'Unknown')}",
            f"  Notification Type: {header.get('notificationType', {}).get('type', 'Unknown')}",
            f"  Section Count: {header.get('sectionCount', 0)}",
        ]
        
        if cper_json.get('_mock'):
            lines.append(f"  [Mock Data - Source: {cper_json.get('_source_file', 'Unknown')}]")
        
        return "\n".join(lines)
    
    def create_cper_record(self, cper_json: Dict[str, Any]) -> CPERRecord:
        """
        Create CPERRecord object from JSON data.
        
        Args:
            cper_json: CPER data in JSON format
            
        Returns:
            CPERRecord: CPER record object
        """
        return CPERRecord.from_json(cper_json)
    
    def create_sppr_cpad_from_cper(self, cper_json: Dict[str, Any], output_path: str = None) -> Optional[str]:
        """
        Create a SPPR (Soft Post Package Repair) CPAD from a CPER analysis.
        
        Only creates SPPR CPAD when:
        - Section type is 'Platform Memory 2' (61ec04fc-48e6-d813-25c9-8daa44750b12)
        - Notification type is 'CMC' (2dce8bb1-bdd7-450e-b9ad-9cf4ebd4f890)
        
        This matches the RasAPI-main Analyzer.create_sppr_cpad_from_cper_json() behavior.
        
        Args:
            cper_json: CPER data in JSON format (from analyze_cper_file)
            output_path: Optional output path for the SPPR CPAD file
            
        Returns:
            str: Path to created SPPR CPAD file, or None if conditions not met
        """
        from datetime import datetime, timedelta
        import json
        
        # Check notification type GUID (must be CMC)
        notification_guid = cper_json.get('header', {}).get('notificationType', {}).get('guid', '')
        cmc_guid = '2dce8bb1-bdd7-450e-b9ad-9cf4ebd4f890'
        
        if notification_guid != cmc_guid:
            if self.verbose:
                logger.info(f"Skipping SPPR CPAD - notification type is not CMC (guid: {notification_guid})")
            return None
        
        # Check section type (must be Platform Memory 2)
        section_descriptors = cper_json.get('sectionDescriptors', [])
        if not section_descriptors:
            if self.verbose:
                logger.info("Skipping SPPR CPAD - no section descriptors found")
            return None
        
        section_type_data = section_descriptors[0].get('sectionType', {}).get('data', '')
        platform_memory_2_guid = '61ec04fc-48e6-d813-25c9-8daa44750b12'
        
        if section_type_data != platform_memory_2_guid:
            if self.verbose:
                logger.info(f"Skipping SPPR CPAD - section type is not Platform Memory 2 (type: {section_type_data})")
            return None
        
        # Conditions met - create SPPR CPAD
        if self.verbose:
            logger.info("Conditions met for SPPR CPAD creation (CMC notification + Platform Memory 2)")
        
        # Load SPPR template
        sppr_template_path = Path(__file__).parent / "templates" / "infoPprCperSourcePoC.json"
        
        # Also check for SPPR CPAD example template
        sppr_cpad_template_path = Path(__file__).parent.parent.parent.parent / "examples" / "ras" / "SpprCpadExample.json"
        
        template_path = sppr_cpad_template_path if sppr_cpad_template_path.exists() else sppr_template_path
        
        if not template_path.exists():
            logger.warning(f"SPPR template not found: {template_path}")
            return None
        
        try:
            with open(template_path, 'r') as f:
                sppr_template = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load SPPR template: {e}")
            return None
        
        # Extract and update timestamp (add 5 seconds to CPER timestamp)
        cper_header = cper_json.get('header', {})
        cper_timestamp_str = cper_header.get('timestamp', datetime.now().isoformat())
        
        try:
            cper_timestamp = datetime.fromisoformat(cper_timestamp_str.replace('Z', '+00:00'))
            new_timestamp = cper_timestamp + timedelta(seconds=5)
            sppr_template['header']['timestamp'] = new_timestamp.isoformat()
        except Exception as e:
            logger.warning(f"Failed to parse timestamp, using current time: {e}")
            sppr_template['header']['timestamp'] = datetime.now().isoformat()
        
        # Copy platformID, creatorID, partitionID from CPER
        if cper_header.get('platformID'):
            sppr_template['header']['platformID'] = cper_header['platformID']
        if cper_header.get('creatorID'):
            sppr_template['header']['creatorID'] = cper_header['creatorID']
        if cper_header.get('partitionID'):
            sppr_template['header']['partitionID'] = cper_header['partitionID']
        
        # Copy memory-related fields from CPER sections
        cper_sections = cper_json.get('sections', [])
        if cper_sections and len(cper_sections) > 0:
            cper_memory2 = cper_sections[0].get('Memory2', {})
            
            # Copy relevant memory fields to SPPR template sections
            if 'sections' in sppr_template and len(sppr_template['sections']) > 0:
                sppr_sections = sppr_template['sections'][0]
                
                # If InfoActionPpr section exists, update with memory info
                if 'InfoActionPpr' in sppr_sections:
                    info_ppr = sppr_sections['InfoActionPpr']
                    
                    # Copy physical address if available
                    if 'physicalAddress' in cper_memory2:
                        info_ppr['physicalAddress'] = cper_memory2['physicalAddress']
                    if 'physicalAddressHex' in cper_memory2:
                        info_ppr['physicalAddressHex'] = cper_memory2['physicalAddressHex']
        
        # Copy FRU info from section descriptors
        cper_section_desc = section_descriptors[0] if section_descriptors else {}
        if 'sectionDescriptors' in sppr_template and len(sppr_template['sectionDescriptors']) > 0:
            sppr_section_desc = sppr_template['sectionDescriptors'][0]
            
            if cper_section_desc.get('fruID'):
                sppr_section_desc['fruID'] = cper_section_desc['fruID']
            if cper_section_desc.get('fruText'):
                sppr_section_desc['fruText'] = cper_section_desc['fruText']
        
        # Determine output path
        if output_path is None:
            output_dir = Path(__file__).parent.parent.parent.parent / "ras_demo_output" / "generated_cpad"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(output_dir / f"sppr_cpad_{timestamp_str}.json")
        
        # Write SPPR CPAD
        try:
            with open(output_path, 'w') as f:
                json.dump(sppr_template, f, indent=2)
            
            if self.verbose:
                logger.info(f"Created SPPR CPAD: {output_path}")
            
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to write SPPR CPAD: {e}")
            return None
    
    def should_recommend_sppr(self, cper_json: Dict[str, Any]) -> bool:
        """
        Check if SPPR (Soft Post Package Repair) should be recommended for a CPER.
        
        SPPR is recommended for corrected memory errors (CMC with Platform Memory 2).
        
        Args:
            cper_json: CPER data in JSON format
            
        Returns:
            bool: True if SPPR is recommended
        """
        # Check notification type (must be CMC for corrected errors)
        notification_guid = cper_json.get('header', {}).get('notificationType', {}).get('guid', '')
        cmc_guid = '2dce8bb1-bdd7-450e-b9ad-9cf4ebd4f890'
        
        if notification_guid != cmc_guid:
            return False
        
        # Check section type (must be memory)
        section_descriptors = cper_json.get('sectionDescriptors', [])
        if not section_descriptors:
            return False
        
        section_type_data = section_descriptors[0].get('sectionType', {}).get('data', '')
        platform_memory_2_guid = '61ec04fc-48e6-d813-25c9-8daa44750b12'
        
        return section_type_data == platform_memory_2_guid


# Convenience functions

def analyze_cper(cper_file_path: str, verbose: bool = False) -> Optional[Dict[str, Any]]:
    """
    Analyze a CPER file and return JSON data.
    
    Args:
        cper_file_path: Path to CPER file
        verbose: Enable verbose output
        
    Returns:
        dict: CPER JSON data, or None if failed
    """
    analyzer = CPERAnalyzer(verbose=verbose)
    return analyzer.analyze_cper_file(cper_file_path)


def get_cper_summary(cper_file_path: str) -> Optional[str]:
    """
    Get summary of CPER file.
    
    Args:
        cper_file_path: Path to CPER file
        
    Returns:
        str: Summary text, or None if failed
    """
    analyzer = CPERAnalyzer()
    cper_json = analyzer.analyze_cper_file(cper_file_path)
    
    if cper_json:
        return analyzer.get_cper_summary(cper_json)
    
    return None
