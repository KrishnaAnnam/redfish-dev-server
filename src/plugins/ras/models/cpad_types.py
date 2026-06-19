"""
CPAD (Common Platform Action Document) Data Models

Defines Python data structures for CPAD documents used in RAS error handling.
Based on the OCP RAS specification.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CPADRevision:
    """CPAD revision information"""
    major: int
    minor: int


@dataclass
class CPADFlags:
    """CPAD header flags"""
    name: str = "HW_ERROR_FLAGS_SIMULATED"
    value: int = 4


@dataclass
class CPADNotificationType:
    """CPAD notification type"""
    guid: str
    type: str


@dataclass
class CPADHeader:
    """CPAD document header"""
    creatorID: str
    platformID: str
    recordID: int
    recordLength: int
    sectionCount: int
    confidence: int
    urgency: bool
    timestamp: str
    timestampIsPrecise: bool
    flags: Dict[str, Any] = field(default_factory=dict)
    notificationType: Dict[str, str] = field(default_factory=dict)
    persistenceInfo: int = 0
    revision: Dict[str, int] = field(default_factory=lambda: {"major": 1, "minor": 0})


@dataclass
class CPADSectionFlags:
    """CPAD section descriptor flags"""
    containmentWarning: bool = False
    errorThresholdExceeded: bool = False
    latentError: bool = False
    overflow: bool = False
    primary: bool = True
    propagated: bool = False
    reset: bool = False
    resourceNotAccessible: bool = False


@dataclass
class CPADSectionType:
    """CPAD section type information"""
    data: str  # GUID
    type: str  # Human-readable type name


@dataclass
class CPADSectionDescriptor:
    """CPAD section descriptor"""
    actionID: Dict[str, str]  # {"code": "0x0006", "name": "Unknown"}
    fruID: str  # GUID
    fruText: str
    sectionLength: int
    sectionOffset: int
    confidence: int
    urgency: bool
    flags: Dict[str, bool] = field(default_factory=dict)
    revision: Dict[str, int] = field(default_factory=lambda: {"major": 1, "minor": 0})
    sectionType: Dict[str, str] = field(default_factory=dict)


@dataclass
class CPADSection:
    """CPAD section data (varies by section type)"""
    section_type: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CPADDocument:
    """Complete CPAD document structure"""
    header: Dict[str, Any]
    sectionDescriptors: List[Dict[str, Any]]
    sections: List[Dict[str, Any]] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CPADDocument':
        """Create CPADDocument from dictionary"""
        return cls(
            header=data.get('header', {}),
            sectionDescriptors=data.get('sectionDescriptors', []),
            sections=data.get('sections', [])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert CPADDocument to dictionary"""
        return {
            'header': self.header,
            'sectionDescriptors': self.sectionDescriptors,
            'sections': self.sections
        }
    
    def validate_structure(self) -> Tuple[bool, Optional[str]]:
        """
        Validate CPAD document structure
        
        Returns:
            tuple: (is_valid, error_message)
        """
        # Check required top-level fields
        if not self.header:
            return False, "Missing 'header' field"
        
        if not self.sectionDescriptors:
            return False, "Missing 'sectionDescriptors' field"
        
        # Check header fields
        required_header_fields = ['creatorID', 'sectionCount', 'platformID']
        for field in required_header_fields:
            if field not in self.header:
                return False, f"Missing '{field}' in header"
        
        # Check section count matches
        declared_count = self.header.get('sectionCount', 0)
        actual_count = len(self.sectionDescriptors)
        if declared_count != actual_count:
            return False, f"Section count mismatch: header declares {declared_count}, but {actual_count} descriptors present"
        
        # Check sectionDescriptors
        if not self.sectionDescriptors:
            return False, "Empty 'sectionDescriptors' array"
        
        # Check first descriptor has actionID
        first_descriptor = self.sectionDescriptors[0]
        if 'actionID' not in first_descriptor:
            return False, "Missing 'actionID' in first sectionDescriptor"
        
        # Validate actionID structure (should be {"code": "0x...", "name": "..."})
        action_id = first_descriptor['actionID']
        if isinstance(action_id, dict):
            if 'code' not in action_id:
                return False, "Missing 'code' in actionID object"
        
        return True, None
    
    def get_creator_id(self) -> str:
        """Get creator ID from header"""
        return self.header.get('creatorID', 'Unknown')
    
    def get_platform_id(self) -> str:
        """Get platform ID from header"""
        return self.header.get('platformID', 'Unknown')
    
    def get_action_id(self) -> str:
        """Get action ID code from first section descriptor.
        
        Returns the hex code string (e.g. '0x0006') from the actionID object
        produced by cpad-convert: {"code": "0x0006", "name": "Unknown"}
        """
        if self.sectionDescriptors:
            action_id = self.sectionDescriptors[0].get('actionID', {})
            if isinstance(action_id, dict):
                return action_id.get('code', 'Unknown')
            return str(action_id)  # fallback for plain value
        return 'Unknown'
    
    def get_confidence(self) -> int:
        """Get confidence level from header"""
        return self.header.get('confidence', 0)


@dataclass
class CPERRecord:
    """CPER (Common Platform Error Record) structure"""
    record_id: str
    timestamp: datetime
    severity: str
    record_type: str
    creator_id: str
    platform_id: str
    sections: List[Dict[str, Any]] = field(default_factory=list)
    raw_data: Optional[bytes] = None
    json_data: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_binary(cls, data: bytes) -> 'CPERRecord':
        """Create CPER record from binary data (requires libcper)"""
        # Placeholder - actual implementation requires libcper
        raise NotImplementedError("Binary CPER parsing requires libcper")
    
    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'CPERRecord':
        """Create CPER record from JSON (libcper output)"""
        return cls(
            record_id=data.get('header', {}).get('recordID', 'unknown'),
            timestamp=datetime.now(),
            severity=data.get('header', {}).get('severity', 'Unknown'),
            record_type=data.get('header', {}).get('notificationType', {}).get('type', 'Unknown'),
            creator_id=data.get('header', {}).get('creatorID', 'Unknown'),
            platform_id=data.get('header', {}).get('platformID', 'Unknown'),
            sections=data.get('sections', []),
            json_data=data
        )
