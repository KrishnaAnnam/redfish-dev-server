#!/usr/bin/env python3
"""
CPER to LogEntry Conversion

Converts Common Platform Error Records (CPER) to Redfish LogEntry format
for storage in the RAS LogService.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import json


class CPERToLogEntry:
    """Converter for CPER to Redfish LogEntry format"""
    
    # Severity mapping from CPER to Redfish
    SEVERITY_MAP = {
        0: "Warning",         # Recoverable/non-fatal uncorrected
        1: "Critical",        # Fatal
        2: "Warning",         # Corrected
        3: "OK",              # Informational
        4: "OK"               # Action Event (proposed)
    }
    
    SEVERITY_NAME_MAP = {
        "Informational": "OK",
        "Corrected": "Warning",
        "Recoverable": "Warning",
        "Uncorrected": "Warning",
        "UncorrectedNonFatal": "Warning",
        "Fatal": "Critical",
        "UncorrectedFatal": "Critical",
        "Action Event": "OK"
    }
    
    @staticmethod
    def convert(cper_data: Dict[str, Any], manager_id: str = "System", 
                entry_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Convert CPER data to Redfish LogEntry format.
        
        Args:
            cper_data: CPER record data (header + sections) OR simple CPAD format
            manager_id: Manager ID for path construction
            entry_id: Optional LogEntry ID (auto-generated if not provided)
            
        Returns:
            dict: Redfish LogEntry resource
        """
        # Handle both full CPER format and simple CPAD format
        if "header" in cper_data and "sectionDescriptors" in cper_data:
            # Full CPER format
            header = cper_data["header"]
            sections = cper_data["sectionDescriptors"]
            
            # Generate entry ID if not provided
            if not entry_id:
                record_id = header.get("recordID", "unknown")
                entry_id = str(record_id) if isinstance(record_id, int) else record_id
            
            # Extract severity
            severity_info = header.get("severity", {})
            severity_code = severity_info.get("code", 0)
            severity_name = severity_info.get("name", "Informational")
            
            # Extract FRU information from first section
            fru_id = None
            fru_text = None
            section_type = "Unknown"
            if sections:
                first_section = sections[0]
                fru_id = first_section.get("fruID")
                fru_text = first_section.get("fruText")
                section_type_info = first_section.get("sectionType", {})
                # Handle both string and dict formats for sectionType
                if isinstance(section_type_info, str):
                    section_type = section_type_info
                else:
                    section_type = section_type_info.get("type", "Unknown")
            
            timestamp = header.get("timestamp", datetime.now(timezone.utc).isoformat())
            record_id_str = header.get("recordID", "unknown")
        else:
            # Simple CPAD format
            sections = []
            severity_code = 0
            
            # For severity mapping, RecordType is more reliable than Severity field
            # RecordType: Informational, Corrected, Fatal
            # Severity: OK, Warning, Critical
            severity_name = cper_data.get("RecordType", cper_data.get("Severity", "Informational"))
            
            # Generate entry ID if not provided
            if not entry_id:
                record_id = cper_data.get("RecordId", "unknown")
                entry_id = str(record_id) if isinstance(record_id, int) else record_id
            
            # Extract FRU info
            fru_id = cper_data.get("FRUId")
            fru_text = cper_data.get("FRUText")
            section_type = cper_data.get("SectionType", "Unknown")
            
            timestamp = cper_data.get("Timestamp", datetime.now(timezone.utc).isoformat())
            record_id_str = cper_data.get("RecordId", "unknown")
            
            # Map RecordType to severity if Severity not provided
            if "Severity" not in cper_data and "RecordType" in cper_data:
                severity_name = cper_data["RecordType"]
        
        # Map to Redfish severity
        redfish_severity = CPERToLogEntry.SEVERITY_NAME_MAP.get(
            severity_name,
            CPERToLogEntry.SEVERITY_MAP.get(severity_code, "OK")
        )
        
        # Build human-readable message
        message = CPERToLogEntry._build_message_simple(cper_data, section_type, fru_id, fru_text, severity_name)
        
        # Build LogEntry
        log_entry = {
            "@odata.type": "#LogEntry.v1_15_0.LogEntry",
            "@odata.id": f"/redfish/v1/Managers/{manager_id}/LogServices/RAS/Entries/{entry_id}",
            "Id": str(entry_id),
            "Name": f"CPER Record {entry_id}",
            "Created": timestamp,
            "EntryType": "Oem",
            "Severity": redfish_severity,
            "Message": message,
            "OemRecordFormat": "RasProto.CPER",
        }
        
        # Add optional fields
        if fru_text:
            log_entry["SensorType"] = fru_text
            log_entry["SensorNumber"] = fru_id or 0
        
        # Add Links section
        links = {}
        if fru_id:
            # Could link to actual FRU resource if available
            links["OriginOfCondition"] = {
                "@odata.id": f"/redfish/v1/Chassis/System/FRU/{fru_id}"
            }
        
        if links:
            log_entry["Links"] = links
        
        # AdditionalDataURI points to the binary CPER attachment
        log_entry["AdditionalDataURI"] = f"/redfish/v1/Managers/{manager_id}/LogServices/RAS/Entries/{entry_id}/Attachment"
        
        return log_entry
    
    @staticmethod
    def _build_message(header: Dict[str, Any], sections: List[Dict[str, Any]]) -> str:
        """
        Build human-readable message from CPER data.
        
        Args:
            header: CPER header
            sections: CPER section descriptors
            
        Returns:
            str: Human-readable message
        """
        severity_name = header.get("severity", {}).get("name", "Unknown")
        notification_type = header.get("notificationType", {}).get("type", "Error")
        
        if sections:
            first_section = sections[0]
            section_type = first_section.get("sectionType", {}).get("type", "Unknown")
            fru_text = first_section.get("fruText", "Unknown Component")
            
            return f"{severity_name} {notification_type}: {section_type} error on {fru_text}"
        
        return f"{severity_name} {notification_type}: Platform error detected"
    
    @staticmethod
    def _build_message_simple(cper_data: Dict[str, Any], section_type: str = "Unknown",
                              fru_id: str = None, fru_text: str = None,
                              severity_name: str = None) -> str:
        """
        Build human-readable message from CPER/CPAD data.
        
        Args:
            cper_data: CPER or CPAD data
            section_type: Section type
            fru_id: FRU ID
            fru_text: FRU description
            severity_name: Pre-extracted severity name (from CPER header)
            
        Returns:
            str: Human-readable message
        """
        record_type = severity_name or cper_data.get("RecordType", cper_data.get("Severity", "Unknown"))
        
        # Action Event CPERs record a completed action, not an error
        if record_type == "Action Event":
            parts = ["Action Event recorded"]
        else:
            parts = [f"{record_type} error detected"]
        
        if section_type and section_type != "Unknown":
            parts.append(f"in {section_type}")
        
        if fru_text:
            parts.append(f"on {fru_text}")
        elif fru_id:
            parts.append(f"(FRU: {fru_id})")
        
        return " ".join(parts)
    
    @staticmethod
    def create_entry_attachment(cper_data: Dict[str, Any]) -> bytes:
        """
        Create attachment data for full CPER record.
        
        Args:
            cper_data: Complete CPER data
            
        Returns:
            bytes: JSON-encoded CPER data
        """
        return json.dumps(cper_data, indent=2).encode('utf-8')
    
    @staticmethod
    def get_severity_from_cper(cper_data: Dict[str, Any]) -> str:
        """
        Extract Redfish severity from CPER data.
        
        Args:
            cper_data: CPER record
            
        Returns:
            str: Redfish severity (OK, Warning, Critical)
        """
        header = cper_data.get("header", {})
        severity_info = header.get("severity", {})
        severity_name = severity_info.get("name", "Informational")
        
        return CPERToLogEntry.SEVERITY_NAME_MAP.get(severity_name, "OK")
    
    @staticmethod
    def extract_fru_info(cper_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract FRU ID and text from CPER.
        
        Args:
            cper_data: CPER record
            
        Returns:
            tuple: (fru_id, fru_text)
        """
        sections = cper_data.get("sectionDescriptors", [])
        if sections:
            first_section = sections[0]
            return (
                first_section.get("fruID"),
                first_section.get("fruText")
            )
        return (None, None)
