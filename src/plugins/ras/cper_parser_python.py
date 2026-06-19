"""
Pure Python CPER/CPAD Binary Parser

Alternative to libcper C library - implements binary format parsing in pure Python.
No compilation required, works on any platform with Python 3.x.

Based on UEFI Specification Appendix N (Common Platform Error Record)
and OCP RAS CPAD specification.
"""

import struct
import uuid
import json
from typing import Dict, Any, List, Optional, BinaryIO
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# UEFI CPER GUIDs (from UEFI Spec Appendix N)
CPER_SECTION_TYPE_GUIDS = {
    # Processor
    uuid.UUID('9876ccad-47b4-4bdb-b65e-16f193c4f3db'): 'Processor Generic',
    uuid.UUID('dc3ea0b0-a144-4797-b95b-53fa242b6e1d'): 'IA32/X64 Processor',
    uuid.UUID('e19e3d16-bc11-11e4-9caa-c2051d5d46b0'): 'ARM Processor',
    
    # Memory
    uuid.UUID('a5bc1114-6f64-4ede-b863-3e83ed7c83b1'): 'Platform Memory',
    uuid.UUID('61EC04FC-48e6-d813-25c9-8da31b4f4db9'): 'Memory Error (2)',
    
    # PCIe
    uuid.UUID('d995e954-bbc1-430f-ad91-b44dcb3c6f35'): 'PCIe',
    uuid.UUID('c5753963-3b84-4095-bf78-eddad3f9c9dd'): 'PCI/PCI-X Bus',
    uuid.UUID('eb5e4685-ca66-4769-b6a2-26068b001326'): 'PCI Component/Device',
    
    # Firmware
    uuid.UUID('81212a96-09ed-4996-9471-8d729c8e69ed'): 'Firmware Error Record',
    
    # CXL (Compute Express Link)
    uuid.UUID('91335ef6-ebfb-4478-a6a6-88b7b8c6b02d'): 'CXL Protocol Error',
    uuid.UUID('fe927475-dd59-4339-a586-79bab113246a'): 'CXL Component Event',
}

# CPAD Action GUIDs (from RasApi)
CPAD_ACTION_GUIDS = {
    uuid.UUID('d5a6a32b-8652-49c9-9f5f-5f6e9f6e9f6e'): 'SPPR (Soft Post Package Repair)',
    uuid.UUID('12345678-1234-5678-1234-567812345678'): 'Memory Error Spoof',
}


class CPERHeader:
    """CPER Record Header (UEFI Spec Table N-1)"""
    
    # Format: little-endian
    FORMAT = '<'
    FORMAT += 'I'      # SignatureStart (0x52455043 = 'CPER')
    FORMAT += 'H'      # Revision
    FORMAT += 'I'      # SignatureEnd
    FORMAT += 'H'      # SectionCount
    FORMAT += 'I'      # ErrorSeverity
    FORMAT += 'I'      # ValidationBits
    FORMAT += 'I'      # RecordLength
    FORMAT += 'Q'      # Timestamp (64-bit)
    FORMAT += '16s'    # PlatformID (GUID)
    FORMAT += '16s'    # PartitionID (GUID)
    FORMAT += '16s'    # CreatorID (GUID)
    FORMAT += '16s'    # NotificationType (GUID)
    FORMAT += 'Q'      # RecordID
    FORMAT += 'I'      # Flags
    FORMAT += 'Q'      # PersistenceInfo
    FORMAT += '12s'    # Reserved
    
    SIZE = struct.calcsize(FORMAT)
    SIGNATURE_START = 0x52455043  # 'CPER'
    
    def __init__(self, data: bytes):
        """Parse CPER header from binary data."""
        if len(data) < self.SIZE:
            raise ValueError(f"CPER header too small: {len(data)} < {self.SIZE}")
        
        unpacked = struct.unpack(self.FORMAT, data[:self.SIZE])
        
        self.signature_start = unpacked[0]
        self.revision = unpacked[1]
        self.signature_end = unpacked[2]
        self.section_count = unpacked[3]
        self.error_severity = unpacked[4]
        self.validation_bits = unpacked[5]
        self.record_length = unpacked[6]
        self.timestamp = unpacked[7]
        self.platform_id = uuid.UUID(bytes_le=unpacked[8])
        self.partition_id = uuid.UUID(bytes_le=unpacked[9])
        self.creator_id = uuid.UUID(bytes_le=unpacked[10])
        self.notification_type = uuid.UUID(bytes_le=unpacked[11])
        self.record_id = unpacked[12]
        self.flags = unpacked[13]
        self.persistence_info = unpacked[14]
        
        # Validate signature
        if self.signature_start != self.SIGNATURE_START:
            raise ValueError(f"Invalid CPER signature: 0x{self.signature_start:08X}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'signatureStart': f"0x{self.signature_start:08X}",
            'revision': self.revision,
            'signatureEnd': f"0x{self.signature_end:08X}",
            'sectionCount': self.section_count,
            'errorSeverity': self.error_severity,
            'validationBits': f"0x{self.validation_bits:08X}",
            'recordLength': self.record_length,
            'timestamp': self.timestamp,
            'platformID': str(self.platform_id),
            'partitionID': str(self.partition_id),
            'creatorID': str(self.creator_id),
            'notificationType': str(self.notification_type),
            'recordID': self.record_id,
            'flags': f"0x{self.flags:08X}",
            'persistenceInfo': self.persistence_info,
        }


class CPERSectionDescriptor:
    """CPER Section Descriptor (UEFI Spec Table N-2)"""
    
    FORMAT = '<'
    FORMAT += 'I'      # SectionOffset
    FORMAT += 'I'      # SectionLength
    FORMAT += 'H'      # Revision
    FORMAT += 'B'      # ValidationBits
    FORMAT += 'B'      # Reserved
    FORMAT += 'I'      # Flags
    FORMAT += '16s'    # SectionType (GUID)
    FORMAT += '16s'    # FRUId (GUID)
    FORMAT += 'I'      # SectionSeverity
    FORMAT += '20s'    # FRUText
    
    SIZE = struct.calcsize(FORMAT)
    
    def __init__(self, data: bytes):
        """Parse section descriptor from binary data."""
        if len(data) < self.SIZE:
            raise ValueError(f"Section descriptor too small: {len(data)} < {self.SIZE}")
        
        unpacked = struct.unpack(self.FORMAT, data[:self.SIZE])
        
        self.section_offset = unpacked[0]
        self.section_length = unpacked[1]
        self.revision = unpacked[2]
        self.validation_bits = unpacked[3]
        self.flags = unpacked[4]
        self.section_type = uuid.UUID(bytes_le=unpacked[5])
        self.fru_id = uuid.UUID(bytes_le=unpacked[6])
        self.section_severity = unpacked[7]
        self.fru_text = unpacked[8].decode('ascii', errors='ignore').rstrip('\x00')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        section_type_name = CPER_SECTION_TYPE_GUIDS.get(
            self.section_type, 
            "Unknown Section Type"
        )
        
        return {
            'sectionOffset': self.section_offset,
            'sectionLength': self.section_length,
            'revision': self.revision,
            'validationBits': f"0x{self.validation_bits:02X}",
            'flags': f"0x{self.flags:08X}",
            'sectionType': str(self.section_type),
            'sectionTypeName': section_type_name,
            'fruID': str(self.fru_id),
            'sectionSeverity': self.section_severity,
            'fruText': self.fru_text if self.fru_text else None,
        }


class CPADHeader:
    """CPAD Document Header (OCP RAS CPAD Spec)"""
    
    FORMAT = '<'
    FORMAT += 'I'      # Signature (0x44415043 = 'CPAD')
    FORMAT += 'H'      # Version
    FORMAT += 'H'      # HeaderLength
    FORMAT += 'I'      # TotalLength
    FORMAT += '16s'    # ActionGUID
    FORMAT += 'I'      # Flags
    FORMAT += 'Q'      # Timestamp
    FORMAT += '32s'    # SubmitterID
    FORMAT += '64s'    # Reserved
    
    SIZE = struct.calcsize(FORMAT)
    SIGNATURE = 0x44415043  # 'CPAD'
    
    def __init__(self, data: bytes):
        """Parse CPAD header from binary data."""
        if len(data) < self.SIZE:
            raise ValueError(f"CPAD header too small: {len(data)} < {self.SIZE}")
        
        unpacked = struct.unpack(self.FORMAT, data[:self.SIZE])
        
        self.signature = unpacked[0]
        self.version = unpacked[1]
        self.header_length = unpacked[2]
        self.total_length = unpacked[3]
        self.action_guid = uuid.UUID(bytes_le=unpacked[4])
        self.flags = unpacked[5]
        self.timestamp = unpacked[6]
        self.submitter_id = unpacked[7].decode('ascii', errors='ignore').rstrip('\x00')
        
        # Validate signature
        if self.signature != self.SIGNATURE:
            raise ValueError(f"Invalid CPAD signature: 0x{self.signature:08X}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        action_name = CPAD_ACTION_GUIDS.get(
            self.action_guid,
            "Unknown Action"
        )
        
        return {
            'signature': f"0x{self.signature:08X}",
            'version': self.version,
            'headerLength': self.header_length,
            'totalLength': self.total_length,
            'actionGUID': str(self.action_guid),
            'actionName': action_name,
            'flags': f"0x{self.flags:08X}",
            'timestamp': self.timestamp,
            'submitterID': self.submitter_id,
        }


class PythonCPERParser:
    """Pure Python CPER binary parser - no C library required."""
    
    def parse_cper_file(self, file_path: str) -> Dict[str, Any]:
        """
        Parse CPER binary file to JSON.
        
        Args:
            file_path: Path to .cper binary file
            
        Returns:
            dict: Parsed CPER data
        """
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            return self.parse_cper_bytes(data)
        except Exception as e:
            logger.error(f"Failed to parse CPER file {file_path}: {e}")
            raise
    
    def parse_cper_bytes(self, data: bytes) -> Dict[str, Any]:
        """
        Parse CPER binary data to dictionary.
        
        Args:
            data: Binary CPER data
            
        Returns:
            dict: Parsed CPER record
        """
        result = {}
        
        # Parse header
        header = CPERHeader(data)
        result['header'] = header.to_dict()
        
        # Parse section descriptors
        offset = CPERHeader.SIZE
        sections = []
        
        for i in range(header.section_count):
            if offset + CPERSectionDescriptor.SIZE > len(data):
                logger.warning(f"Truncated section descriptor {i}")
                break
            
            desc = CPERSectionDescriptor(data[offset:])
            sections.append(desc.to_dict())
            
            # Extract raw section data
            if desc.section_offset + desc.section_length <= len(data):
                section_data = data[desc.section_offset:desc.section_offset + desc.section_length]
                sections[-1]['rawData'] = section_data.hex()
                sections[-1]['rawDataSize'] = len(section_data)
            
            offset += CPERSectionDescriptor.SIZE
        
        result['sections'] = sections
        result['sectionCount'] = len(sections)
        
        return result
    
    def cper_to_json_file(self, cper_path: str, json_path: str):
        """
        Convert CPER binary to JSON file.
        
        Args:
            cper_path: Input .cper file
            json_path: Output .json file
        """
        cper_data = self.parse_cper_file(cper_path)
        
        with open(json_path, 'w') as f:
            json.dump(cper_data, f, indent=2)
        
        logger.info(f"Converted {cper_path} -> {json_path}")


class PythonCPADParser:
    """Pure Python CPAD binary parser - no C library required."""
    
    def parse_cpad_file(self, file_path: str) -> Dict[str, Any]:
        """
        Parse CPAD binary file to JSON.
        
        Args:
            file_path: Path to .cpad binary file
            
        Returns:
            dict: Parsed CPAD data
        """
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            return self.parse_cpad_bytes(data)
        except Exception as e:
            logger.error(f"Failed to parse CPAD file {file_path}: {e}")
            raise
    
    def parse_cpad_bytes(self, data: bytes) -> Dict[str, Any]:
        """
        Parse CPAD binary data to dictionary.
        
        Args:
            data: Binary CPAD data
            
        Returns:
            dict: Parsed CPAD document
        """
        result = {}
        
        # Parse header
        header = CPADHeader(data)
        result['header'] = header.to_dict()
        
        # Parse payload (JSON after header)
        payload_offset = header.header_length
        if payload_offset < len(data):
            payload_data = data[payload_offset:header.total_length]
            try:
                # CPAD payload is typically JSON
                payload_str = payload_data.decode('utf-8')
                result['payload'] = json.loads(payload_str)
            except (UnicodeDecodeError, json.JSONDecodeError):
                # If not JSON, store as hex
                result['payload'] = payload_data.hex()
                result['payloadFormat'] = 'binary'
        
        return result
    
    def cpad_to_json_file(self, cpad_path: str, json_path: str):
        """
        Convert CPAD binary to JSON file.
        
        Args:
            cpad_path: Input .cpad file
            json_path: Output .json file
        """
        cpad_data = self.parse_cpad_file(cpad_path)
        
        with open(json_path, 'w') as f:
            json.dump(cpad_data, f, indent=2)
        
        logger.info(f"Converted {cpad_path} -> {json_path}")


# Convenience functions
def parse_cper(file_or_bytes) -> Dict[str, Any]:
    """
    Parse CPER from file path or bytes.
    
    Args:
        file_or_bytes: Path to .cper file or bytes object
        
    Returns:
        dict: Parsed CPER data
    """
    parser = PythonCPERParser()
    
    if isinstance(file_or_bytes, (str, Path)):
        return parser.parse_cper_file(str(file_or_bytes))
    elif isinstance(file_or_bytes, bytes):
        return parser.parse_cper_bytes(file_or_bytes)
    else:
        raise TypeError("Input must be file path or bytes")


def parse_cpad(file_or_bytes) -> Dict[str, Any]:
    """
    Parse CPAD from file path or bytes.
    
    Args:
        file_or_bytes: Path to .cpad file or bytes object
        
    Returns:
        dict: Parsed CPAD data
    """
    parser = PythonCPADParser()
    
    if isinstance(file_or_bytes, (str, Path)):
        return parser.parse_cpad_file(str(file_or_bytes))
    elif isinstance(file_or_bytes, bytes):
        return parser.parse_cpad_bytes(file_or_bytes)
    else:
        raise TypeError("Input must be file path or bytes")


if __name__ == '__main__':
    # Demo usage
    import sys
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        
        if input_file.endswith('.cper'):
            print("Parsing CPER file...")
            data = parse_cper(input_file)
            print(json.dumps(data, indent=2))
        elif input_file.endswith('.cpad'):
            print("Parsing CPAD file...")
            data = parse_cpad(input_file)
            print(json.dumps(data, indent=2))
        else:
            print("Unknown file type (expected .cper or .cpad)")
    else:
        print("Usage: python cper_parser_python.py <file.cper|file.cpad>")
