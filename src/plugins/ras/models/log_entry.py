#!/usr/bin/env python3
"""
CPER to LogEntry Conversion

Converts Common Platform Error Records (CPER) to Redfish LogEntry format
per OCP RAS API Workstream Specification §4.

LogService: /redfish/v1/Managers/{ManagerId}/LogServices/CPER
Pattern A:  DiagnosticData (inline base64) for small CPERs
Pattern B:  AdditionalDataURI (attachment) for large CPERs
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import json
import base64

# Threshold in bytes: CPERs below this are inline (Pattern A), above are attachment (Pattern B)
INLINE_CPER_THRESHOLD = 4096


class CPERToLogEntry:
    """Converter for CPER to Redfish LogEntry format per OCP RAS API §4"""
    
    # §4.7 CPER Severity Mapping
    SEVERITY_MAP = {
        0: "Critical",        # Recoverable (Uncorrected) → Critical
        1: "Critical",        # Fatal → Critical
        2: "Warning",         # Corrected → Warning
        3: "OK",              # Informational → OK
        4: "Warning"          # PlatformActionStatus → Warning
    }
    
    SEVERITY_NAME_MAP = {
        "Informational": "OK",
        "Corrected": "Warning",
        "Recoverable": "Critical",
        "Uncorrected": "Critical",
        "UncorrectedNonFatal": "Critical",
        "Fatal": "Critical",
        "UncorrectedFatal": "Critical",
        "Action Event": "Warning"
    }
    
    # §4.6 RAS API Queue Mapping
    QUEUE_MESSAGE_ID_MAP = {
        "Fatal": "OCPRAS.1.0.0.FatalError",
        "UncorrectedFatal": "OCPRAS.1.0.0.FatalError",
        "Recoverable": "OCPRAS.1.0.0.UncorrectedError",
        "Uncorrected": "OCPRAS.1.0.0.UncorrectedError",
        "UncorrectedNonFatal": "OCPRAS.1.0.0.UncorrectedError",
        "Corrected": "OCPRAS.1.0.0.CorrectedError",
        "Informational": "OCPRAS.1.0.0.InformationalEvent",
        "Action Event": "OCPRAS.1.0.0.PlatformActionEvent",
    }
    
    QUEUE_TYPE_MAP = {
        "Fatal": "Fatal",
        "UncorrectedFatal": "Fatal",
        "Recoverable": "Recoverable",
        "Uncorrected": "Recoverable",
        "UncorrectedNonFatal": "Recoverable",
        "Corrected": "Corrected",
        "Informational": "Informational",
        "Action Event": "PlatformActionStatus",
    }
    
    @staticmethod
    def convert(cper_data: Dict[str, Any], manager_id: str = "System", 
                entry_id: Optional[str] = None,
                binary_cper: Optional[bytes] = None) -> Dict[str, Any]:
        """
        Convert CPER data to Redfish LogEntry format per OCP RAS API §4.3-4.5.
        
        Produces Pattern A (inline DiagnosticData) for CPERs < INLINE_CPER_THRESHOLD,
        or Pattern B (AdditionalDataURI) for larger records.
        
        Args:
            cper_data: CPER record data (header + sections) OR simple CPAD format
            manager_id: Manager ID for path construction
            entry_id: Optional LogEntry ID (auto-generated if not provided)
            binary_cper: Optional raw binary CPER bytes (for size check and inline encoding)
            
        Returns:
            dict: Redfish LogEntry resource per §4.3
        """
        # Extract fields from either full CPER or simple format
        if "header" in cper_data and "sectionDescriptors" in cper_data:
            header = cper_data["header"]
            sections = cper_data.get("sectionDescriptors", [])
            
            if not entry_id:
                record_id = header.get("recordID", "unknown")
                entry_id = str(record_id) if isinstance(record_id, int) else record_id
            
            severity_info = header.get("severity", {})
            severity_code = severity_info.get("code", 0)
            severity_name = severity_info.get("name", "Informational")
            
            timestamp = header.get("timestamp", datetime.now(timezone.utc).isoformat())
            record_id_value = header.get("recordID")
            platform_id = header.get("platformID", "")
            partition_id = header.get("partitionID", "")
            
            # Extract section info for message
            section_type = "Unknown"
            fru_text = None
            if sections:
                first_section = sections[0]
                fru_text = first_section.get("fruText")
                section_type_info = first_section.get("sectionType", {})
                if isinstance(section_type_info, str):
                    section_type = section_type_info
                else:
                    section_type = section_type_info.get("type", "Unknown")
        else:
            # Simple CPAD format
            severity_name = cper_data.get("RecordType", cper_data.get("Severity", "Informational"))
            
            if not entry_id:
                record_id = cper_data.get("RecordId", "unknown")
                entry_id = str(record_id) if isinstance(record_id, int) else record_id
            
            timestamp = cper_data.get("Timestamp", datetime.now(timezone.utc).isoformat())
            record_id_value = cper_data.get("RecordId")
            platform_id = cper_data.get("PlatformID", "")
            partition_id = cper_data.get("PartitionID", "")
            section_type = cper_data.get("SectionType", "Unknown")
            fru_text = cper_data.get("FRUText")
            severity_code = None
        
        # §4.7 Map to Redfish severity
        redfish_severity = CPERToLogEntry.SEVERITY_NAME_MAP.get(
            severity_name,
            CPERToLogEntry.SEVERITY_MAP.get(severity_code, "OK") if severity_code is not None else "OK"
        )
        
        # §4.6 Map to MessageId
        message_id = CPERToLogEntry.QUEUE_MESSAGE_ID_MAP.get(
            severity_name, "OCPRAS.1.0.0.InformationalEvent"
        )
        
        # §4.6 Map to QueueType
        queue_type = CPERToLogEntry.QUEUE_TYPE_MAP.get(
            severity_name, "Informational"
        )
        
        # Build human-readable message
        message = CPERToLogEntry._build_message_for_queue(queue_type, section_type, fru_text)
        
        # §4.3 Base LogEntry
        log_entry_path = f"/redfish/v1/Managers/{manager_id}/LogServices/CPER/Entries/{entry_id}"
        log_entry = {
            "@odata.type": "#LogEntry.v1_17_0.LogEntry",
            "@odata.id": log_entry_path,
            "Id": str(entry_id),
            "Name": "CPER Log Entry",
            "EntryType": "Oem",
            "OemRecordFormat": "CPER",
            "Severity": redfish_severity,
            "Created": timestamp,
            "Message": message,
            "MessageId": message_id,
            "DiagnosticDataType": "CPER",
        }
        
        # §4.4 / §4.5 Pattern selection
        cper_size = len(binary_cper) if binary_cper else 0
        
        if binary_cper and cper_size <= INLINE_CPER_THRESHOLD:
            # Pattern A: inline base64
            log_entry["DiagnosticData"] = base64.b64encode(binary_cper).decode("ascii")
        else:
            # Pattern B: AdditionalDataURI
            log_entry["AdditionalDataURI"] = f"{log_entry_path}/Attachment"
            if cper_size > 0:
                log_entry["AdditionalDataSizeBytes"] = cper_size
        
        # §4.3 OEM metadata
        log_entry["Oem"] = {
            "OCPRASAPIWS": {
                "PlatformID": platform_id,
                "PartitionID": partition_id,
                "RecordID": record_id_value if record_id_value else int(entry_id) if entry_id.isdigit() else entry_id,
                "QueueType": queue_type
            }
        }
        
        return log_entry
    
    @staticmethod
    def _build_message_for_queue(queue_type: str, section_type: str = "Unknown",
                                  fru_text: str = None) -> str:
        """Build human-readable message based on queue type."""
        messages = {
            "Fatal": "Fatal platform error recorded.",
            "Recoverable": "Uncorrected recoverable error recorded.",
            "Corrected": "Corrected memory error recorded.",
            "Informational": "Informational event recorded.",
            "PlatformActionStatus": "Platform action result recorded.",
        }
        return messages.get(queue_type, "Error recorded.")
    
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
