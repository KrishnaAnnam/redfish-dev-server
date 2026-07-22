"""
CPAD Handler

Handles CPAD (Common Platform Action Document) validation, processing,
and submission to the RAS Service.

Extracted and adapted from RasApi-main/submit_cpad.py
"""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, Any

from .models.cpad_types import CPADDocument

logger = logging.getLogger(__name__)


class CPADHandler:
    """Handler for CPAD document processing and validation."""
    
    def __init__(self):
        """Initialize CPAD handler."""
        pass
    
    def load_cpad_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Load and validate CPAD JSON file.
        
        Args:
            file_path: Path to the CPAD JSON file
            
        Returns:
            dict: CPAD data, or None if error
        """
        try:
            with open(file_path, 'r') as f:
                cpad_data = json.load(f)
            
            logger.info(f"Loaded CPAD file: {file_path}")
            return cpad_data
            
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading CPAD file {file_path}: {e}")
            return None
    
    def validate_cpad_structure(self, cpad_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate CPAD structure against expected schema.
        
        Args:
            cpad_data: CPAD data to validate
            
        Returns:
            tuple: (is_valid, error_message)
        """
        # Create CPAD document and validate
        cpad_doc = CPADDocument.from_dict(cpad_data)
        return cpad_doc.validate_structure()
    
    def extract_cpad_metadata(self, cpad_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract key metadata from CPAD document.
        
        Args:
            cpad_data: CPAD document data
            
        Returns:
            dict: Extracted metadata
        """
        header = cpad_data.get('header', {})
        section_descriptors = cpad_data.get('sectionDescriptors', [])
        first_descriptor = section_descriptors[0] if section_descriptors else {}
        
        return {
            'creator_id': header.get('creatorID', 'Unknown'),
            'platform_id': header.get('platformID', 'Unknown'),
            'partition_id': header.get('partitionID', 'Unknown'),
            'record_id': header.get('recordID', 0),
            'record_length': header.get('recordLength', 0),
            'timestamp': header.get('timestamp', ''),
            'confidence': header.get('confidence', 0),
            'urgency': header.get('urgency', False),
            'section_count': header.get('sectionCount', 0),
            'action_id': self._extract_action_code(first_descriptor),
            'fru_id': first_descriptor.get('fruID', 'Unknown'),
            'fru_text': first_descriptor.get('fruText', 'Unknown'),
        }
    
    @staticmethod
    def _extract_action_code(descriptor: Dict[str, Any]) -> str:
        """Extract action code from sectionDescriptor's actionID field.
        
        cpad-convert produces: {"actionID": {"code": "0x0006", "name": "Unknown"}}
        Returns the hex code string, e.g. '0x0006'.
        """
        action_id = descriptor.get('actionID', {})
        if isinstance(action_id, dict):
            return action_id.get('code', 'Unknown')
        return str(action_id)  # fallback

    def format_cpad_summary(self, cpad_data: Dict[str, Any]) -> str:
        """
        Format CPAD data into human-readable summary.
        
        Args:
            cpad_data: CPAD document data
            
        Returns:
            str: Formatted summary
        """
        metadata = self.extract_cpad_metadata(cpad_data)
        
        summary_lines = [
            "CPAD Document Summary:",
            f"  Creator ID: {metadata['creator_id']}",
            f"  Platform ID: {metadata['platform_id']}",
            f"  Record ID: {metadata['record_id']}",
            f"  Timestamp: {metadata['timestamp']}",
            f"  Confidence: {metadata['confidence']}%",
            f"  Urgency: {metadata['urgency']}",
            f"  Section Count: {metadata['section_count']}",
            f"  Action ID: {metadata['action_id']}",
            f"  FRU: {metadata['fru_text']} ({metadata['fru_id']})",
        ]
        
        return "\n".join(summary_lines)
    
    def convert_cpad_to_redfish_payload(self, cpad_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert CPAD document to Redfish action payload format.
        
        This is used when submitting CPAD via the SubmitCPAD action.
        
        Args:
            cpad_data: CPAD document data
            
        Returns:
            dict: Redfish-formatted action payload
        """
        return {
            "CPADData": cpad_data
        }
    
    def validate_and_extract(self, cpad_data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Validate CPAD and extract metadata in one operation.
        
        Args:
            cpad_data: CPAD document data
            
        Returns:
            tuple: (is_valid, metadata_dict, error_message)
        """
        # Validate structure
        is_valid, error_msg = self.validate_cpad_structure(cpad_data)
        
        if not is_valid:
            return False, None, error_msg
        
        # Extract metadata
        metadata = self.extract_cpad_metadata(cpad_data)
        
        return True, metadata, None


# Convenience functions for common operations

def validate_cpad_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a CPAD file.
    
    Args:
        file_path: Path to CPAD JSON file
        
    Returns:
        tuple: (is_valid, error_message)
    """
    handler = CPADHandler()
    cpad_data = handler.load_cpad_file(file_path)
    
    if cpad_data is None:
        return False, "Failed to load CPAD file"
    
    return handler.validate_cpad_structure(cpad_data)


def load_and_validate_cpad(file_path: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Load and validate a CPAD file in one operation.
    
    Args:
        file_path: Path to CPAD JSON file
        
    Returns:
        tuple: (cpad_data, error_message)
    """
    handler = CPADHandler()
    cpad_data = handler.load_cpad_file(file_path)
    
    if cpad_data is None:
        return None, "Failed to load CPAD file"
    
    is_valid, error_msg = handler.validate_cpad_structure(cpad_data)
    
    if not is_valid:
        return None, error_msg
    
    return cpad_data, None


def extract_cpad_summary(cpad_data: Dict[str, Any]) -> str:
    """
    Get human-readable summary of CPAD document.
    
    Args:
        cpad_data: CPAD document data
        
    Returns:
        str: Formatted summary
    """
    handler = CPADHandler()
    return handler.format_cpad_summary(cpad_data)
