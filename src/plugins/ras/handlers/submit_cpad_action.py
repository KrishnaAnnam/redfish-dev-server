"""
SubmitCPAD Action Handler

Handles the SubmitCPAD action which processes CPAD (Common Platform Action Document)
submissions and executes the requested actions.

Endpoint: POST /redfish/v1/Managers/{ManagerId}/Oem/RasProto/RASService/Actions/RasProto.SubmitCPAD
"""

import logging
import struct
import subprocess
import tempfile
import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path

from ..cpad_handler import CPADHandler
from ..message_utils import (
    cpad_received,
    cpad_validated,
    cpad_action_completed,
    cpad_action_failed,
)
from .log_service import RASLogServiceHandler
from .event_service import RASEventServiceHandler

logger = logging.getLogger(__name__)


class SubmitCPADActionHandler:
    """Handler for SubmitCPAD action processing."""
    
    def __init__(self, mockup_dir: Optional[str] = None, event_handler: Optional[RASEventServiceHandler] = None):
        """
        Initialize SubmitCPAD action handler.
        
        Args:
            mockup_dir: Path to mockup directory (for LogService integration)
            event_handler: Optional event handler for emitting events
        """
        self.logger = logger  # Use module-level logger
        self.event_handler = event_handler
        self.cpad_handler = CPADHandler()
        self.submission_history = []
        self.mockup_dir = mockup_dir
        
        # Initialize LogService handler if mockup directory provided
        self.log_service_handler = None
        if mockup_dir:
            try:
                self.log_service_handler = RASLogServiceHandler(mockup_dir)
                logger.info("RAS LogService integration enabled")
            except Exception as e:
                logger.warning(f"RAS LogService integration disabled: {e}")
    
    def handle_post(self, manager_id: str, request_body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """
        Handle POST request to SubmitCPAD action.
        
        Args:
            manager_id: Manager ID
            request_body: Request body containing CPADData
            
        Returns:
            tuple: (status_code, response_body)
        """
        return self.handle_submit_cpad(manager_id, request_body)
    
    def _locate_cpad_convert(self):
        """
        Locate the cpad-convert tool in the project's libcper build directory.
        
        Returns:
            str: Path to cpad-convert, or None if not found
        """
        # Look relative to this file: handlers/ -> ras/ -> libcper/build/
        plugin_dir = Path(__file__).resolve().parent.parent
        build_dir = plugin_dir / 'libcper' / 'build'
        cpad_convert = build_dir / 'cpad-convert'
        
        if cpad_convert.exists():
            return str(cpad_convert), str(build_dir)
        
        return None, None
    
    @staticmethod
    def _cleanup_temp_path(path):
        """Remove a temp file and its parent directory if it was created by mkdtemp."""
        if not path:
            return
        try:
            import shutil
            parent = os.path.dirname(path)
            if os.path.basename(parent).startswith('ras_cper_'):
                shutil.rmtree(parent, ignore_errors=True)
            elif os.path.exists(path):
                os.unlink(path)
        except OSError:
            pass
    
    def _convert_binary_cpad_to_json(self, raw_data: bytes) -> Optional[Dict[str, Any]]:
        """
        Convert binary CPAD to JSON using cpad-convert tool.
        
        Args:
            raw_data: Raw binary CPAD data
            
        Returns:
            dict: Parsed CPAD JSON, or None if conversion failed
        """
        cpad_convert, build_dir = self._locate_cpad_convert()
        if not cpad_convert:
            logger.error("cpad-convert tool not found at libcper/build/cpad-convert")
            return None
        
        tmp_path = None
        try:
            # Write binary CPAD to a temp file
            with tempfile.NamedTemporaryFile(suffix='.cpad', delete=False) as tmp:
                tmp.write(raw_data)
                tmp_path = tmp.name
            
            # Run cpad-convert to-json
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = build_dir + ':' + env.get('LD_LIBRARY_PATH', '')
            
            cmd = [cpad_convert, 'to-json', tmp_path]
            logger.info(f"Running cpad-convert: {' '.join(cmd)}")
            
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=build_dir,
                env=env
            )
            stdout, stderr = proc.communicate(timeout=10)
            
            if proc.returncode != 0:
                logger.error(f"cpad-convert failed: {stderr.decode('utf-8', errors='replace')}")
                return None
            
            # Parse the JSON output from stdout
            cpad_json = json.loads(stdout.decode('utf-8'))
            logger.info("Successfully converted binary CPAD to JSON")
            return cpad_json
            
        except subprocess.TimeoutExpired:
            logger.error("cpad-convert timed out")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse cpad-convert output as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in binary CPAD conversion: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def handle_submit_cpad(self, manager_id: str, request_body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """
        Handle POST request to SubmitCPAD action.
        
        Accepts Base64-encoded binary CPAD:
            {EncodingType: "Base64", CPADData: "<b64-encoded-binary-cpad>"}
        
        The plugin decodes the base64, validates the CPAD signature, and
        converts binary CPAD to JSON using cperlib (cpad-convert).
        
        Args:
            manager_id: Manager ID
            request_body: Request body with EncodingType and CPADData
            
        Returns:
            tuple: (status_code, response_body)
        """
        import base64 as b64mod
        import struct
        
        print(f"\n{'=' * 80}")
        print(f"\t\t\t\tRAS PLUGIN: PROCESSING CPAD SUBMISSION")
        print(f"{'=' * 80}")
        
        # Validate required fields
        if (request_body.get('EncodingType') != 'Base64' or
                'CPADData' not in request_body):
            return self._error_response(
                400,
                'Base.1.16.ActionParameterMissing',
                "SubmitCPAD requires {EncodingType: 'Base64', CPADData: '<base64>'}.",
                ['EncodingType', 'CPADData']
            )
        
        print(f"\n   Step 1: Received Base64-encoded binary CPAD")
        logger.info("Processing Base64-encoded binary CPAD submission")
        
        # Decode base64 to raw bytes
        try:
            raw_data = b64mod.b64decode(request_body['CPADData'])
        except Exception as e:
            print(f"           ✗ Base64 decode failed: {e}")
            return self._error_response(
                400,
                'Base.1.16.MalformedJSON',
                f'Failed to decode Base64 CPADData: {e}',
                ['CPADData']
            )
        
        # Validate CPAD signature
        CPAD_SIGNATURE_START = 0x44415043  # "CPAD" in little-endian
        CPAD_HEADER_MIN_SIZE = 48
        
        if len(raw_data) < CPAD_HEADER_MIN_SIZE:
            print(f"           ✗ Binary CPAD too small: {len(raw_data)} bytes")
            return self._error_response(
                400,
                'OCPRAS.1.0.CPADValidationFailed',
                f'Binary CPAD too small: {len(raw_data)} bytes (minimum {CPAD_HEADER_MIN_SIZE})',
                [str(len(raw_data))]
            )
        
        sig = struct.unpack('<I', raw_data[0:4])[0]
        if sig != CPAD_SIGNATURE_START:
            print(f"           ✗ Invalid CPAD signature: 0x{sig:08X}")
            return self._error_response(
                400,
                'OCPRAS.1.0.CPADValidationFailed',
                f'Invalid CPAD signature: 0x{sig:08X}',
                [f'0x{sig:08X}']
            )
        
        print(f"           ✓ Valid CPAD signature, {len(raw_data)} bytes")
        
        # Use cpad-convert to decode binary CPAD to JSON
        print(f"\n   Step 2: Converting binary CPAD to JSON using cperlib (cpad-convert)")
        cpad_data = self._convert_binary_cpad_to_json(raw_data)
        
        if cpad_data is None:
            print(f"           ✗ cpad-convert could not decode binary CPAD")
            return self._error_response(
                500,
                'OCPRAS.1.0.CPADConversionFailed',
                'Failed to convert binary CPAD to JSON using cpad-convert tool.',
                ['cpad-convert']
            )
        
        print(f"           ✓ Binary CPAD decoded to JSON")
        logger.info("Binary CPAD decoded to JSON successfully")
        
        # Step 3: Validate CPAD structure
        print(f"\n   Step 3: Validating CPAD structure")
        logger.info(f"Validating CPAD submission for Manager: {manager_id}")
        is_valid, metadata, error_msg = self.cpad_handler.validate_and_extract(cpad_data)
        
        if not is_valid:
            print(f"           ✗ {error_msg}")
            logger.warning(f"CPAD validation failed: {error_msg}")
            return self._error_response(
                400,
                'OCPRAS.1.0.CPADValidationFailed',
                f"CPAD validation failed: {error_msg}",
                [error_msg]
            )
        
        print(f"           ✓ Valid CPAD structure confirmed")
        print(f"           RecordID:   {metadata['record_id']}")
        print(f"           CreatorID:  {metadata['creator_id']}")
        print(f"           PlatformID: {metadata['platform_id']}")
        print(f"           ActionID:   {metadata['action_id']}")
        logger.info(f"CPAD validated successfully - Action: {metadata['action_id']}")
        
        # Emit CPAD received event
        if self.event_handler:
            try:
                self.event_handler.emit_cpad_received(
                    manager_id,
                    f"CPAD-{metadata['record_id']}",
                    cpad_data
                )
            except Exception as e:
                logger.error(f"Failed to emit CPAD received event: {e}")
        
        # Step 4: Create LogEntry from CPER (if LogService available)
        log_entry_id = None
        severity = self._map_action_to_severity(metadata['action_id'])
        
        # Describe the action
        ACTION_DESCRIPTIONS = {
            '0x0006': 'Injection: spoofing corrected memory error',
            '0x8001': 'SPPR: soft post package repair operation',
        }
        action_desc = ACTION_DESCRIPTIONS.get(metadata['action_id'], f"Action {metadata['action_id']}")
        
        if self.log_service_handler:
            try:
                print(f"\n   Step 4: ActionID {metadata['action_id']} identified as: {action_desc}")
                
                # --- 4a: Error CPER (Corrected) — only for non-SPPR actions ---
                #     SPPR (0x8001) only produces an Action Event CPER, not an
                #     informational error CPER.
                if metadata['action_id'] != '0x8001':
                    print(f"           Creating {severity} error CPER...")
                    cper_json_data = self._convert_cpad_to_cper(cpad_data, metadata)
                    logger.debug(f"Generated CPER JSON data from template")
                    
                    cper_binary_path = self._convert_json_to_binary_cper(cper_json_data, metadata)
                    if cper_binary_path:
                        logger.info(f"Created binary CPER: {cper_binary_path}")
                    status, entry_id = self.log_service_handler.add_cper_log_entry(cper_json_data, cper_binary_path)
                    self._cleanup_temp_path(cper_binary_path)
                    
                    if status == 201:
                        log_entry_id = entry_id
                        print(f"           ✓ {severity} CPER LogEntry: {entry_id}")
                        logger.info(f"Created RAS LogEntry: {entry_id}")
                    else:
                        print(f"           ✗ {severity} CPER LogEntry status: {status}")
                
                # --- 4b: Action Event CPER ---
                print(f"           Creating Action Event CPER...")
                ae_cper_json = self._create_action_event_cper(cpad_data, metadata, action_return_code=0x00)
                ae_binary_path = self._convert_json_to_binary_cper(ae_cper_json, metadata)
                ae_status, ae_entry_id = self.log_service_handler.add_cper_log_entry(ae_cper_json, ae_binary_path)
                self._cleanup_temp_path(ae_binary_path)
                if ae_status == 201:
                    log_entry_id = log_entry_id or ae_entry_id
                    print(f"           ✓ Action Event CPER LogEntry: {ae_entry_id}")
                    logger.info(f"Created Action Event LogEntry: {ae_entry_id}")
                else:
                    print(f"           ✗ Action Event CPER LogEntry status: {ae_status}")
                
            except Exception as e:
                import traceback
                print(f"           ✗ Error creating LogEntry: {e}")
                logger.error(f"Failed to create LogEntry: {e}")
                logger.error(traceback.format_exc())
        else:
            print(f"\n   Step 4: LogService not available, skipping CPER creation")
        
        # Emit CPAD approved event
        if self.event_handler:
            try:
                self.event_handler.emit_cpad_approved(
                    manager_id,
                    f"CPAD-{metadata['record_id']}",
                    metadata['action_id'],
                    log_entry_id
                )
            except Exception as e:
                logger.error(f"Failed to emit CPAD approved event: {e}")
        
        # Record submission
        self._record_submission(manager_id, metadata, 'APPROVED', log_entry_id)
        
        # Build success response
        response = self._build_success_response(manager_id, metadata, log_entry_id)
        print(f"\n{'=' * 80}")
        print(f"\t\t\t\tCPAD ActionID {metadata['action_id']} -- Successful")
        print(f"{'=' * 80}\n")
        return 202, response
    
    def _build_success_response(self, manager_id: str, metadata: Dict[str, Any], 
                               log_entry_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Build success response for approved CPAD.
        
        Args:
            manager_id: Manager ID
            metadata: CPAD metadata
            log_entry_id: Optional LogEntry ID where CPER was stored
            
        Returns:
            dict: Response body
        """
        # Generate task ID for tracking
        task_id = f"CPAD-{metadata['record_id']}-{int(datetime.now().timestamp())}"
        
        messages = [
            cpad_received(str(metadata['record_id']), metadata['action_id']),
            cpad_validated(str(metadata['record_id'])),
        ]
        
        # Add LogEntry creation message if available
        if log_entry_id:
            messages.append({
                'MessageId': 'OCPRAS.1.0.CPERRecordCreated',
                'Message': f'CPER record created in LogService: {log_entry_id}',
                'MessageArgs': [log_entry_id],
                'Severity': 'OK',
                'RelatedProperties': [f'/redfish/v1/Managers/{manager_id}/LogServices/RAS/Entries/{log_entry_id}']
            })
        
        response = {
            '@odata.type': '#Task.v1_7_1.Task',
            '@odata.id': f'/redfish/v1/TaskService/Tasks/{task_id}',
            'Id': task_id,
            'Name': 'Submit CPAD Task',
            'TaskState': 'Running',
            'TaskStatus': 'OK',
            'StartTime': datetime.now().isoformat(),
            'Messages': messages,
            'Payload': {
                'HttpHeaders': [],
                'HttpOperation': 'POST',
                'JsonBody': json.dumps({
                    'ActionId': metadata['action_id'],
                    'RecordId': metadata['record_id'],
                    'FRU': metadata['fru_text'],
                    'Confidence': metadata['confidence']
                }),
                'TargetUri': f'/redfish/v1/Managers/{manager_id}/Oem/RasProto/RASService'
            }
        }
        
        # Add LogEntry link if available
        if log_entry_id:
            response['Links'] = {
                'LogEntry': {
                    '@odata.id': f'/redfish/v1/Managers/{manager_id}/LogServices/RAS/Entries/{log_entry_id}'
                }
            }
        
        return response
    
    def _error_response(self, status_code: int, message_id: str, message: str, args: list) -> Tuple[int, Dict[str, Any]]:
        """
        Build error response.
        
        Args:
            status_code: HTTP status code
            message_id: Redfish message ID
            message: Error message
            args: Message arguments
            
        Returns:
            tuple: (status_code, response_body)
        """
        return status_code, {
            'error': {
                '@Message.ExtendedInfo': [{
                    'MessageId': message_id,
                    'Message': message,
                    'MessageArgs': args,
                    'Severity': 'Warning',
                    'Resolution': 'Correct the request body and resubmit.'
                }]
            }
        }
    
    def _record_submission(self, manager_id: str, metadata: Dict[str, Any], 
                          decision: str, log_entry_id: Optional[str] = None) -> None:
        """
        Record CPAD submission in history.
        
        Args:
            manager_id: Manager ID
            metadata: CPAD metadata
            decision: Policy decision (APPROVED/DENIED)
            log_entry_id: Optional LogEntry ID where CPER was stored
        """
        submission = {
            'timestamp': datetime.now().isoformat(),
            'manager_id': manager_id,
            'record_id': metadata['record_id'],
            'action_id': metadata['action_id'],
            'creator_id': metadata['creator_id'],
            'platform_id': metadata['platform_id'],
            'confidence': metadata['confidence'],
            'decision': decision
        }
        
        if log_entry_id:
            submission['log_entry_id'] = log_entry_id
        
        self.submission_history.append(submission)
        
        # Keep only last 100 submissions
        if len(self.submission_history) > 100:
            self.submission_history = self.submission_history[-100:]
    
    def get_submission_history(self) -> list:
        """Get CPAD submission history."""
        return self.submission_history.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics on CPAD submissions.
        
        Returns:
            dict: Statistics summary
        """
        total = len(self.submission_history)
        if total == 0:
            return {
                'total_submissions': 0,
                'approved': 0,
                'denied': 0,
                'approval_rate': 0.0
            }
        
        approved = sum(1 for s in self.submission_history if s['decision'] == 'APPROVED')
        denied = total - approved
        
        return {
            'total_submissions': total,
            'approved': approved,
            'denied': denied,
            'approval_rate': (approved / total) * 100 if total > 0 else 0.0
        }
    
    def get_handler_routes(self) -> Dict[str, Any]:
        """
        Get route mappings for this handler.
        
        Returns:
            dict: Route patterns and handler methods
        """
        return {
            'POST': {
                r'/redfish/v1/Managers/(?P<manager_id>[^/]+)/Oem/RasProto/RASService/Actions/RasProto\.SubmitCPAD$': self.handle_submit_cpad,
            }
        }
    
    def _convert_cpad_to_cper(self, cpad_data: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert CPAD (Action Document) to CPER (Error Record) using template-based approach.
        
        Follows RasAPI-main implementation: loads CPER template and merges CPAD data.
        
        Args:
            cpad_data: Original CPAD data
            metadata: Extracted CPAD metadata
            
        Returns:
            dict: CPER data structure
        """
        import os
        import json
        from datetime import datetime, timedelta
        
        action_id = metadata['action_id']
        
        # Map action_id to template file (following RasAPI-main)
        # Action IDs are hex codes from cpad-convert (e.g. "0x0006", "0x8001")
        ACTION_ID_TEMPLATE_MAP = {
            '0x0006': 'memCperSourcePoC.json',     # Memory Error Spoof
            '0x8001': 'infoPprCperSourcePoC.json',  # SPPR (Soft Post Package Repair)
        }
        
        template_filename = ACTION_ID_TEMPLATE_MAP.get(action_id)
        if not template_filename:
            self.logger.error(f"Unsupported ActionID in CPAD to CPER conversion: {action_id}")
            raise ValueError(f"Unsupported action ID: {action_id}")
        
        # Load template file
        template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', template_filename)
        template_path = os.path.abspath(template_path)
        
        if not os.path.exists(template_path):
            self.logger.error(f"Template file not found: {template_path}")
            raise FileNotFoundError(f"CPER template not found: {template_path}")
        
        with open(template_path, 'r') as f:
            template_data = json.load(f)
        
        # Extract data from CPAD
        cpad_header = cpad_data.get('header', {})
        cpad_section_desc = cpad_data.get('sectionDescriptors', [{}])[0]
        
        # Generate unique recordID for each CPER (template has a static placeholder)
        import time
        import random
        unique_record_id = int(time.time() * 1000) % (2**31) + random.randint(0, 9999)
        template_data['header']['recordID'] = unique_record_id
        
        # Update template with CPAD values (following RasAPI-main merge logic)
        template_data['header']['creatorID'] = cpad_header.get('creatorID')
        template_data['header']['platformID'] = cpad_header.get('platformID')
        
        # Copy partitionID if present in CPAD
        if 'partitionID' in cpad_header:
            template_data['header']['partitionID'] = cpad_header.get('partitionID')
        
        # Add 5 minutes to timestamp (following RasAPI-main)
        original_timestamp = cpad_header.get('timestamp', datetime.now().isoformat() + '+00:00')
        try:
            dt = datetime.fromisoformat(original_timestamp.replace('Z', '+00:00'))
            new_dt = dt + timedelta(minutes=5)
            template_data['header']['timestamp'] = new_dt.isoformat().replace('+00:00', '+00:00')
        except Exception as e:
            self.logger.warning(f"Failed to parse timestamp, using template default: {e}")
        
        # Copy FRU information
        template_data['sectionDescriptors'][0]['fruID'] = cpad_section_desc.get('fruID')
        template_data['sectionDescriptors'][0]['fruText'] = cpad_section_desc.get('fruText')
        
        # Merge flags - handle both dict and int formats
        if 'flags' in cpad_section_desc:
            template_flags = template_data['sectionDescriptors'][0].get('flags', {})
            cpad_flags = cpad_section_desc['flags']
            
            # If CPAD flags is a dict, merge with template flags
            if isinstance(cpad_flags, dict):
                # Merge: start with CPAD flags, then override with template flags
                merged_flags = cpad_flags.copy()
                merged_flags.update(template_flags)
                template_data['sectionDescriptors'][0]['flags'] = merged_flags
            # If CPAD flags is an int, keep template flags (template takes priority)
            # This follows RasAPI behavior where template structure is preferred
        
        # Copy sections data (e.g., InfoActionPpr data from CPAD)
        cpad_sections = cpad_data.get('sections', [])
        if cpad_sections and len(cpad_sections) > 0:
            # For PPR action, copy InfoActionPpr data if present
            if action_id == '0x8001' and 'InfoActionPpr' in cpad_sections[0]:
                template_data['sections'][0]['InfoActionPpr'] = cpad_sections[0]['InfoActionPpr']
            # For memory error spoofing, copy Memory2 data if present
            elif action_id == '0x0006' and 'Memory2' in cpad_sections[0]:
                template_data['sections'][0]['Memory2'] = cpad_sections[0]['Memory2']
        
        return template_data
    
    def _locate_cper_convert(self):
        """
        Locate the cper-convert tool in the project's libcper build directory.
        
        Returns:
            tuple: (path_to_cper_convert, build_dir) or (None, None)
        """
        plugin_dir = Path(__file__).resolve().parent.parent
        build_dir = plugin_dir / 'libcper' / 'build'
        cper_convert = build_dir / 'cper-convert'
        
        if cper_convert.exists():
            return str(cper_convert), str(build_dir)
        
        return None, None
    
    def _convert_json_to_binary_cper(self, cper_json_data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """
        Convert JSON CPER to binary CPER format using cper-convert tool from libcper.
        
        Args:
            cper_json_data: CPER data in JSON format
            metadata: CPAD metadata (for severity determination)
            
        Returns:
            str: Path to binary CPER file, or None if conversion failed
        """
        cper_convert, build_dir = self._locate_cper_convert()
        if not cper_convert:
            self.logger.warning("cper-convert tool not found at libcper/build/cper-convert")
            return None
        
        try:
            action_id = metadata['action_id']
            severity = self._map_action_to_severity(action_id)
            
            # Create temp directory for JSON and binary files
            temp_dir = tempfile.mkdtemp(prefix='ras_cper_')
            json_path = os.path.join(temp_dir, f'{severity.lower()}_cper.json')
            binary_path = os.path.join(temp_dir, f'{severity.lower()}_cper.cper')
            
            # Save JSON CPER to temp file
            with open(json_path, 'w') as f:
                json.dump(cper_json_data, f, indent=2)
            
            # Run cper-convert: JSON -> binary
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = build_dir + ':' + env.get('LD_LIBRARY_PATH', '')
            
            cmd = [cper_convert, 'to-cper', json_path, '--out', binary_path]
            self.logger.info(f"Running: {' '.join(cmd)}")
            
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=build_dir,
                env=env
            )
            stdout, stderr = proc.communicate(timeout=10)
            
            if proc.returncode != 0:
                self.logger.error(f"cper-convert failed: {stderr.decode('utf-8', errors='replace')}")
                return None
            
            if not os.path.exists(binary_path):
                self.logger.error(f"Binary CPER file not created: {binary_path}")
                return None
            
            self.logger.info(f"Successfully converted to binary CPER: {binary_path}")
            return binary_path
            
        except subprocess.TimeoutExpired:
            self.logger.error("cper-convert timed out after 10 seconds")
            return None
        except Exception as e:
            self.logger.error(f"Error converting to binary CPER: {e}")
            return None
    
    def _create_action_event_cper(self, cpad_data: Dict[str, Any], metadata: Dict[str, Any],
                                   action_return_code: int = 0x00) -> Dict[str, Any]:
        """
        Create an Action Event CPER that records which CPAD action was performed.
        
        This is a separate CPER record (severity=4, "Action Event") that captures
        the source CPAD fields so the action can be traced back to its origin.
        
        Uses cperlib's PlatformActionEvent JSON format:
            recordIdValid, sectionIndexValid, actionIdValid, actionReturnCodeValid,
            additionalContextValid   — boolean validation bits
            actionReturnCode         — hex string (0x00=success)
            cpadPlatformID/PartitionID/CreatorID — GUID strings
            cpadRecordId             — hex string (uint64)
            cpadActionId             — hex string (uint16)
            cpadSectionIndex         — unsigned int
            additionalContext        — base64-encoded string
        
        Args:
            cpad_data: Original CPAD JSON data
            metadata: Extracted CPAD metadata
            action_return_code: Result of the action (0x00 = success)
            
        Returns:
            dict: Action Event CPER JSON data (cperlib-compatible)
        """
        import time
        import random
        import base64
        
        # Load Action Event CPER template
        template_path = os.path.join(os.path.dirname(__file__), '..', 'templates', 'actionEventCperTemplate.json')
        template_path = os.path.abspath(template_path)
        
        with open(template_path, 'r') as f:
            ae_cper = json.load(f)
        
        cpad_header = cpad_data.get('header', {})
        cpad_section_desc = cpad_data.get('sectionDescriptors', [{}])[0]
        
        # --- Header ---
        unique_record_id = int(time.time() * 1000) % (2**31) + random.randint(0, 9999)
        ae_cper['header']['recordID'] = unique_record_id
        ae_cper['header']['platformID'] = cpad_header.get('platformID', '00000000-0000-0000-0000-000000000000')
        ae_cper['header']['partitionID'] = cpad_header.get('partitionID', '00000000-0000-0000-0000-000000000000')
        ae_cper['header']['creatorID'] = cpad_header.get('creatorID', '00000000-0000-0000-0000-000000000000')
        ae_cper['header']['timestamp'] = datetime.now().isoformat() + '+00:00'
        
        # --- Section Descriptor ---
        ae_cper['sectionDescriptors'][0]['fruID'] = cpad_section_desc.get('fruID', '00000000-0000-0000-0000-000000000000')
        ae_cper['sectionDescriptors'][0]['fruText'] = cpad_section_desc.get('fruText', '')
        
        # --- PlatformActionEvent Section (cperlib format) ---
        ae_section = ae_cper['sections'][0]['PlatformActionEvent']
        
        # Validation bits (individual booleans — cperlib format)
        ae_section['recordIdValid'] = True
        ae_section['sectionIndexValid'] = True
        ae_section['actionIdValid'] = True
        ae_section['actionReturnCodeValid'] = True
        ae_section['additionalContextValid'] = True
        
        # Action return code as hex string
        ae_section['actionReturnCode'] = f'0x{action_return_code:02x}'
        
        # Source CPAD GUIDs
        ae_section['cpadPlatformID'] = cpad_header.get('platformID', '00000000-0000-0000-0000-000000000000')
        ae_section['cpadPartitionID'] = cpad_header.get('partitionID', '00000000-0000-0000-0000-000000000000')
        ae_section['cpadCreatorID'] = cpad_header.get('creatorID', '00000000-0000-0000-0000-000000000000')
        
        # Record ID as hex string (uint64)
        record_id = cpad_header.get('recordID', 0)
        ae_section['cpadRecordId'] = f'0x{record_id:016x}'
        
        # Action ID as hex string (uint16) — metadata['action_id'] is already "0x0006" etc.
        ae_section['cpadActionId'] = metadata['action_id']
        
        # Section descriptor index
        ae_section['cpadSectionIndex'] = 0
        
        # Additional context: base64-encode a description string
        ACTION_DESCRIPTIONS = {
            '0x0006': 'Memory Error Spoof injection',
            '0x8001': 'Soft Post Package Repair (SPPR)',
        }
        context_str = ACTION_DESCRIPTIONS.get(metadata['action_id'], f"Action {metadata['action_id']}")
        ae_section['additionalContext'] = base64.b64encode(context_str.encode('utf-8')).decode('ascii')
        
        return ae_cper

    def _map_action_to_severity(self, action_id: str) -> str:
        """Map action ID (hex code from cpad-convert) to CPER severity level"""
        SEVERITY_MAP = {
            '0x0006': 'Corrected',       # Memory Error Spoof
            '0x8001': 'Informational',   # SPPR
        }
        return SEVERITY_MAP.get(action_id, 'Informational')
