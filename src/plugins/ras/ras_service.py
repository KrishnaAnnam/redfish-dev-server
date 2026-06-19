#!/usr/bin/env python3
"""
RAS Service Implementation

Reliability, Availability, and Serviceability (RAS) Service for BMC Redfish Simulator.
Based on DMTF Redfish-Mockup-Server.
This service manages RAS endpoints, initiators, error queues, and provides RAS-related actions.

Based on the GEN_10 mockup data structure.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple


class RASServiceHandler:
    """Handler for RAS Service endpoints"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("RASService")
        self.service_enabled = True
        
        # RAS Service collections
        self.endpoints = {}
        self.initiators = {}
        self.error_queues = {
            "IB": {  # In-Band
                "Informational": [],
                "Corrected": [],
                "UncorrectedNonFatal": [],
                "UncorrectedFatal": []
            },
            "OOB": {  # Out-of-Band
                "Informational": [],
                "Corrected": [],
                "UncorrectedNonFatal": [],
                "UncorrectedFatal": []
            }
        }
        
        # Initialize with sample data
        self._initialize_sample_data()
        
    def _initialize_sample_data(self):
        """Initialize RAS service with sample endpoints and initiators"""
        
        # Sample endpoints
        self.endpoints["Endpoint-1"] = {
            "@odata.type": "#Endpoint.v1_0_0.Endpoint",
            "@odata.id": "/redfish/v1/RASService/Endpoints/Endpoint-1",
            "Id": "Endpoint-1",
            "Name": "CPU RAS Endpoint",
            "Description": "A RAS API-compliant endpoint for CPU components",
            "Status": {"State": "Enabled", "Health": "OK"},
            "EndpointType": "CPU",
            "PartitionId": "Partition-001",
            "CreatorId": "BMC-RAS-001",
            "PlatformId": "Platform-Node-001",
            "FRUId": "CPU-Socket-0",
            "FRUText": "CPU Socket 0",
            "CPER": {
                "Timestamp": datetime.utcnow().isoformat() + "Z",
                "PlatformID": "UUID-Platform-001",
                "PartitionID": "UUID-Partition-001", 
                "CreatorID": "BMC-RAS-Creator-001",
                "RecordID": "CPER-0001",
                "FRUID": "CPU-Socket-0",
                "FRUText": "CPU Socket 0"
            }
        }
        
        self.endpoints["Endpoint-2"] = {
            "@odata.type": "#Endpoint.v1_0_0.Endpoint",
            "@odata.id": "/redfish/v1/RASService/Endpoints/Endpoint-2",
            "Id": "Endpoint-2", 
            "Name": "Memory RAS Endpoint",
            "Description": "A RAS API-compliant endpoint for memory components",
            "Status": {"State": "Enabled", "Health": "OK"},
            "EndpointType": "Memory",
            "PartitionId": "Partition-001",
            "CreatorId": "BMC-RAS-001",
            "PlatformId": "Platform-Node-001",
            "FRUId": "DIMM-A1",
            "FRUText": "Memory Module A1",
            "CPER": {
                "Timestamp": datetime.utcnow().isoformat() + "Z",
                "PlatformID": "UUID-Platform-001",
                "PartitionID": "UUID-Partition-001",
                "CreatorID": "BMC-RAS-Creator-001", 
                "RecordID": "CPER-0002",
                "FRUID": "DIMM-A1",
                "FRUText": "Memory Module A1"
            }
        }
        
        # Sample initiators
        self.initiators["Initiator-1"] = {
            "@odata.type": "#Initiator.v1_0_0.Initiator",
            "@odata.id": "/redfish/v1/RASService/Initiators/Initiator-1",
            "Id": "Initiator-1",
            "Name": "BMC RAS Initiator",
            "Description": "BMC entity that initiates RAS API actions",
            "Status": {"State": "Enabled", "Health": "OK"},
            "InitiatorType": "BMC",
            "SupportedActions": ["SubmitCPAD", "CollectCPER"],
            "SupportedEndpoints": [
                {"@odata.id": "/redfish/v1/RASService/Endpoints/Endpoint-1"},
                {"@odata.id": "/redfish/v1/RASService/Endpoints/Endpoint-2"}
            ],
            "CPAD": {
                "Urgency": 1,
                "Confidence": 95,
                "PlatformID": "UUID-Platform-001",
                "PartitionID": "UUID-Partition-001", 
                "CreatorID": "BMC-RAS-Creator-001",
                "NotificationType": "A3F1C9D27B4E8F01",
                "RecordID": "CPAD-0001",
                "SectionCount": 1,
                "Sections": []
            }
        }
        
        self.initiators["Initiator-2"] = {
            "@odata.type": "#Initiator.v1_0_0.Initiator",
            "@odata.id": "/redfish/v1/RASService/Initiators/Initiator-2", 
            "Id": "Initiator-2",
            "Name": "OS RAS Initiator",
            "Description": "Operating system entity that initiates RAS API actions",
            "Status": {"State": "Enabled", "Health": "OK"},
            "InitiatorType": "OS",
            "SupportedActions": ["SubmitCPAD"],
            "SupportedEndpoints": [
                {"@odata.id": "/redfish/v1/RASService/Endpoints/Endpoint-1"}
            ],
            "CPAD": {
                "Urgency": 2,
                "Confidence": 85,
                "PlatformID": "UUID-Platform-001",
                "PartitionID": "UUID-Partition-001",
                "CreatorID": "OS-RAS-Creator-001", 
                "NotificationType": "B4G2D0E38C5F9G02",
                "RecordID": "CPAD-0002",
                "SectionCount": 0,
                "Sections": []
            }
        }
        
    def handle_get(self, path, query_params=None, cached_links=None):
        """Handle GET requests for RAS Service"""
        
        if path == "/redfish/v1/RASService" or path == "/redfish/v1/RASService/":
            return self._get_ras_service()
        
        elif path == "/redfish/v1/RASService/Endpoints" or path == "/redfish/v1/RASService/Endpoints/":
            return self._get_endpoints_collection()
        
        elif path.startswith("/redfish/v1/RASService/Endpoints/"):
            endpoint_id = path.split("/")[-1]
            if endpoint_id in self.endpoints:
                return self._get_endpoint(endpoint_id)
        
        elif path == "/redfish/v1/RASService/Initiators" or path == "/redfish/v1/RASService/Initiators/":
            return self._get_initiators_collection()
        
        elif path.startswith("/redfish/v1/RASService/Initiators/"):
            initiator_id = path.split("/")[-1]
            if initiator_id in self.initiators:
                return self._get_initiator(initiator_id)
        
        elif path == "/redfish/v1/RASService/ErrorQueues" or path == "/redfish/v1/RASService/ErrorQueues/":
            return self._get_error_queues_collection()
        
        elif path.startswith("/redfish/v1/RASService/ErrorQueues/"):
            return self._get_error_queue(path)
        
        return 404, {}, {"error": "RAS Service resource not found"}
    
    def handle_post(self, path, data, cached_links=None):
        """Handle POST requests for RAS Service actions"""
        
        if path == "/redfish/v1/RASService/Actions/SubmitRASAction":
            return self._submit_ras_action(data)
        
        elif path == "/redfish/v1/RASService/Actions/CollectErrorLogs":
            return self._collect_error_logs(data)
        
        elif path.startswith("/redfish/v1/RASService/Endpoints/") and path.endswith("/Actions/SubmitCPAD"):
            endpoint_id = path.split("/")[-3]  # Extract endpoint ID
            return self._submit_cpad(endpoint_id, data)
        
        elif path.startswith("/redfish/v1/RASService/Endpoints/") and path.endswith("/Actions/GetCPERLogs"):
            endpoint_id = path.split("/")[-3]
            return self._get_cper_logs(endpoint_id, data)
        
        elif path.startswith("/redfish/v1/RASService/Initiators/") and path.endswith("/Actions/DispatchCPAD"):
            initiator_id = path.split("/")[-3]
            return self._dispatch_cpad(initiator_id, data)
        
        elif path.startswith("/redfish/v1/RASService/Initiators/") and path.endswith("/Actions/CollectCPER"):
            initiator_id = path.split("/")[-3]
            return self._collect_cper(initiator_id, data)
        
        elif path == "/redfish/v1/RASService/Endpoints/Actions/EndpointCollection.CreateEndpoint":
            return self._create_endpoint(data)
        
        elif path == "/redfish/v1/RASService/Initiators/Actions/InitiatorCollection.CreateInitiator":
            return self._create_initiator(data)
        
        return 404, {}, {"error": "RAS Service action not found"}
    
    def _get_ras_service(self):
        """Get RAS Service root"""
        return 200, {}, {
            "@odata.type": "#RASService.v1_0_0.RASService",
            "@odata.id": "/redfish/v1/RASService",
            "Id": "RASService",
            "Name": "RAS Service",
            "Description": "Service for managing RAS Endpoints, Initiators, and Error Queues",
            "ServiceEnabled": self.service_enabled,
            "Status": {
                "State": "Enabled" if self.service_enabled else "Disabled",
                "Health": "OK"
            },
            "Endpoints": {
                "@odata.id": "/redfish/v1/RASService/Endpoints"
            },
            "Initiators": {
                "@odata.id": "/redfish/v1/RASService/Initiators"
            },
            "ErrorQueues": {
                "@odata.id": "/redfish/v1/RASService/ErrorQueues"
            },
            "Actions": {
                "#RASService.SubmitRASAction": {
                    "target": "/redfish/v1/RASService/Actions/SubmitRASAction",
                    "title": "Submit a RAS action"
                },
                "#RASService.CollectErrorLogs": {
                    "target": "/redfish/v1/RASService/Actions/CollectErrorLogs",
                    "title": "Collect error logs from RAS endpoints"
                }
            }
        }
    
    def _get_endpoints_collection(self):
        """Get RAS Endpoints collection"""
        members = [{"@odata.id": f"/redfish/v1/RASService/Endpoints/{endpoint_id}"} 
                  for endpoint_id in self.endpoints.keys()]
        
        return 200, {}, {
            "@odata.type": "#EndpointCollection.EndpointCollection",
            "@odata.id": "/redfish/v1/RASService/Endpoints",
            "Id": "Endpoints",
            "Name": "RAS Endpoint Collection",
            "Description": "Collection of RAS API-compliant Endpoints",
            "Members@odata.count": len(members),
            "Members": members,
            "@Redfish.CollectionCapabilities": {
                "@odata.type": "#CollectionCapabilities.v1_1_0.CollectionCapabilities",
                "Capabilities": [
                    {
                        "UseCase": "EndpointCreation",
                        "TargetCollection": {
                            "@odata.id": "/redfish/v1/RASService/Endpoints"
                        }
                    }
                ]
            },
            "Actions": {
                "#EndpointCollection.CreateEndpoint": {
                    "target": "/redfish/v1/RASService/Endpoints/Actions/EndpointCollection.CreateEndpoint",
                    "title": "Create a new RAS Endpoint"
                }
            }
        }
    
    def _get_endpoint(self, endpoint_id):
        """Get specific RAS endpoint"""
        endpoint = self.endpoints[endpoint_id].copy()
        
        # Add actions
        endpoint["Actions"] = {
            "#Endpoint.SubmitCPAD": {
                "target": f"/redfish/v1/RASService/Endpoints/{endpoint_id}/Actions/SubmitCPAD",
                "title": "Submit CPAD (Corrective and Predictive Action Directive)"
            },
            "#Endpoint.GetCPERLogs": {
                "target": f"/redfish/v1/RASService/Endpoints/{endpoint_id}/Actions/GetCPERLogs",
                "title": "Get CPER (Common Platform Error Record) logs"
            }
        }
        
        return 200, {}, endpoint
    
    def _get_initiators_collection(self):
        """Get RAS Initiators collection"""
        members = [{"@odata.id": f"/redfish/v1/RASService/Initiators/{initiator_id}"} 
                  for initiator_id in self.initiators.keys()]
        
        return 200, {}, {
            "@odata.type": "#InitiatorCollection.InitiatorCollection",
            "@odata.id": "/redfish/v1/RASService/Initiators",
            "Id": "Initiators",
            "Name": "RAS Initiator Collection",
            "Description": "Collection of RAS API Initiators",
            "Members@odata.count": len(members),
            "Members": members,
            "@Redfish.CollectionCapabilities": {
                "@odata.type": "#CollectionCapabilities.v1_1_0.CollectionCapabilities",
                "Capabilities": [
                    {
                        "UseCase": "InitiatorCreation",
                        "TargetCollection": {
                            "@odata.id": "/redfish/v1/RASService/Initiators"
                        }
                    }
                ]
            },
            "Actions": {
                "#InitiatorCollection.CreateInitiator": {
                    "target": "/redfish/v1/RASService/Initiators/Actions/InitiatorCollection.CreateInitiator",
                    "title": "Create a new RAS Initiator"
                }
            }
        }
    
    def _get_initiator(self, initiator_id):
        """Get specific RAS initiator"""
        initiator = self.initiators[initiator_id].copy()
        
        # Add actions
        initiator["Actions"] = {
            "#Initiator.DispatchCPAD": {
                "target": f"/redfish/v1/RASService/Initiators/{initiator_id}/Actions/DispatchCPAD",
                "title": "Dispatch CPAD to endpoints"
            },
            "#Initiator.CollectCPER": {
                "target": f"/redfish/v1/RASService/Initiators/{initiator_id}/Actions/CollectCPER", 
                "title": "Collect CPER logs from endpoints"
            }
        }
        
        return 200, {}, initiator
    
    def _get_error_queues_collection(self):
        """Get Error Queues collection"""
        members = []
        
        # Add all error queue paths
        for band in ["IB", "OOB"]:
            for severity in ["Informational", "Corrected", "UncorrectedNonFatal", "UncorrectedFatal"]:
                members.append({
                    "@odata.id": f"/redfish/v1/RASService/ErrorQueues/{band}/{severity}"
                })
        
        return 200, {}, {
            "@odata.type": "#ErrorQueueCollection.v1_0_0.ErrorQueueCollection",
            "@odata.id": "/redfish/v1/RASService/ErrorQueues",
            "Id": "ErrorQueues",
            "Name": "Error Queue Collection", 
            "Description": "Collection of severity-based error reporting queues separated by In-Band and Out-of-Band paths",
            "Members@odata.count": len(members),
            "Members": members
        }
    
    def _get_error_queue(self, path):
        """Get specific error queue"""
        path_parts = path.split("/")
        
        if len(path_parts) >= 6:
            band = path_parts[-2]  # IB or OOB
            severity = path_parts[-1]  # Informational, Corrected, etc.
            
            if band in self.error_queues and severity in self.error_queues[band]:
                queue = self.error_queues[band][severity]
                
                return 200, {}, {
                    "@odata.type": "#ErrorQueue.v1_0_0.ErrorQueue",
                    "@odata.id": path,
                    "Id": f"{band}_{severity}",
                    "Name": f"{band} {severity} Error Queue",
                    "Description": f"{band} error queue for {severity} severity errors",
                    "QueueType": band,
                    "Severity": severity,
                    "ErrorCount": len(queue),
                    "MaxQueueSize": 1000,
                    "Errors": queue[-10:] if queue else []  # Last 10 errors
                }
        
        return 404, {}, {"error": "Error queue not found"}
    
    def _submit_ras_action(self, data):
        """Submit a RAS action"""
        action_type = data.get("ActionType", "Unknown")
        target_endpoint = data.get("TargetEndpoint")
        
        self.logger.info(f"Submitting RAS action: {action_type}")
        
        # Simulate action processing
        action_id = f"RAS-Action-{uuid.uuid4().hex[:8]}"
        
        # Add to error queue if this represents an error
        if action_type in ["ErrorReport", "Alert"]:
            severity = data.get("Severity", "Informational")
            band = data.get("Band", "OOB")
            
            error_record = {
                "Id": action_id,
                "Timestamp": datetime.utcnow().isoformat() + "Z",
                "ActionType": action_type,
                "Severity": severity,
                "TargetEndpoint": target_endpoint,
                "Description": data.get("Description", "RAS action submitted"),
                "Data": data
            }
            
            if band in self.error_queues and severity in self.error_queues[band]:
                self.error_queues[band][severity].append(error_record)
        
        return 202, {}, {
            "Message": f"RAS action {action_type} submitted successfully",
            "ActionId": action_id,
            "Status": "InProgress",
            "TargetEndpoint": target_endpoint
        }
    
    def _collect_error_logs(self, data):
        """Collect error logs from RAS endpoints"""
        endpoint_filter = data.get("EndpointFilter", [])
        severity_filter = data.get("SeverityFilter", [])
        
        self.logger.info("Collecting error logs from RAS endpoints")
        
        collected_logs = []
        
        # Collect from all error queues
        for band in self.error_queues:
            for severity in self.error_queues[band]:
                if not severity_filter or severity in severity_filter:
                    for error in self.error_queues[band][severity]:
                        if not endpoint_filter or error.get("TargetEndpoint") in endpoint_filter:
                            collected_logs.append(error)
        
        return 200, {}, {
            "Message": "Error logs collected successfully",
            "CollectionId": f"Collection-{uuid.uuid4().hex[:8]}",
            "LogCount": len(collected_logs),
            "Logs": collected_logs[-50:]  # Return last 50 logs
        }
    
    def _submit_cpad(self, endpoint_id, data):
        """Submit CPAD to specific endpoint"""
        if endpoint_id not in self.endpoints:
            return 404, {}, {"error": "Endpoint not found"}
        
        self.logger.info(f"Submitting CPAD to endpoint {endpoint_id}")
        
        cpad_id = f"CPAD-{uuid.uuid4().hex[:8]}"
        
        return 202, {}, {
            "Message": f"CPAD submitted to endpoint {endpoint_id}",
            "CPADId": cpad_id,
            "Status": "Processing",
            "Endpoint": f"/redfish/v1/RASService/Endpoints/{endpoint_id}"
        }
    
    def _get_cper_logs(self, endpoint_id, data):
        """Get CPER logs from specific endpoint"""
        if endpoint_id not in self.endpoints:
            return 404, {}, {"error": "Endpoint not found"}
        
        self.logger.info(f"Getting CPER logs from endpoint {endpoint_id}")
        
        # Return sample CPER logs
        cper_logs = [
            {
                "RecordId": f"CPER-{endpoint_id}-001",
                "Timestamp": datetime.utcnow().isoformat() + "Z",
                "Severity": "Corrected",
                "ErrorType": "Memory",
                "FRUId": self.endpoints[endpoint_id]["FRUId"],
                "Details": "Correctable memory error detected and corrected"
            }
        ]
        
        return 200, {}, {
            "Message": f"CPER logs retrieved from endpoint {endpoint_id}",
            "LogCount": len(cper_logs),
            "Logs": cper_logs
        }
    
    def _dispatch_cpad(self, initiator_id, data):
        """Dispatch CPAD from initiator"""
        if initiator_id not in self.initiators:
            return 404, {}, {"error": "Initiator not found"}
        
        target_endpoints = data.get("TargetEndpoints", [])
        self.logger.info(f"Dispatching CPAD from initiator {initiator_id} to {len(target_endpoints)} endpoints")
        
        dispatch_id = f"Dispatch-{uuid.uuid4().hex[:8]}"
        
        return 202, {}, {
            "Message": f"CPAD dispatched from initiator {initiator_id}",
            "DispatchId": dispatch_id,
            "Status": "InProgress",
            "TargetEndpoints": target_endpoints
        }
    
    def _collect_cper(self, initiator_id, data):
        """Collect CPER from initiator"""
        if initiator_id not in self.initiators:
            return 404, {}, {"error": "Initiator not found"}
        
        self.logger.info(f"Collecting CPER from initiator {initiator_id}")
        
        return 200, {}, {
            "Message": f"CPER collection initiated by initiator {initiator_id}",
            "CollectionId": f"CPER-Collection-{uuid.uuid4().hex[:8]}",
            "Status": "Completed"
        }
    
    def _create_endpoint(self, data):
        """Create new RAS endpoint"""
        endpoint_id = data.get("Id") or f"Endpoint-{len(self.endpoints) + 1}"
        
        if endpoint_id in self.endpoints:
            return 409, {}, {"error": "Endpoint already exists"}
        
        new_endpoint = {
            "@odata.type": "#Endpoint.v1_0_0.Endpoint",
            "@odata.id": f"/redfish/v1/RASService/Endpoints/{endpoint_id}",
            "Id": endpoint_id,
            "Name": data.get("Name", f"RAS Endpoint {endpoint_id}"),
            "Description": data.get("Description", "RAS API-compliant endpoint"),
            "Status": {"State": "Enabled", "Health": "OK"},
            "EndpointType": data.get("EndpointType", "Generic"),
            "PartitionId": data.get("PartitionId", "Default-Partition"),
            "CreatorId": data.get("CreatorId", "BMC-RAS"),
            "PlatformId": data.get("PlatformId", "Platform-Default"),
            "FRUId": data.get("FRUId", f"FRU-{endpoint_id}"),
            "FRUText": data.get("FRUText", f"Hardware component {endpoint_id}"),
            "CPER": {
                "Timestamp": datetime.utcnow().isoformat() + "Z",
                "PlatformID": data.get("PlatformId", "Platform-Default"),
                "PartitionID": data.get("PartitionId", "Default-Partition"),
                "CreatorID": data.get("CreatorId", "BMC-RAS"),
                "RecordID": f"CPER-{endpoint_id}",
                "FRUID": data.get("FRUId", f"FRU-{endpoint_id}"),
                "FRUText": data.get("FRUText", f"Hardware component {endpoint_id}")
            }
        }
        
        self.endpoints[endpoint_id] = new_endpoint
        self.logger.info(f"Created RAS endpoint {endpoint_id}")
        
        return 201, {"Location": f"/redfish/v1/RASService/Endpoints/{endpoint_id}"}, new_endpoint
    
    def _create_initiator(self, data):
        """Create new RAS initiator"""
        initiator_id = data.get("Id") or f"Initiator-{len(self.initiators) + 1}"
        
        if initiator_id in self.initiators:
            return 409, {}, {"error": "Initiator already exists"}
        
        new_initiator = {
            "@odata.type": "#Initiator.v1_0_0.Initiator",
            "@odata.id": f"/redfish/v1/RASService/Initiators/{initiator_id}",
            "Id": initiator_id,
            "Name": data.get("Name", f"RAS Initiator {initiator_id}"),
            "Description": data.get("Description", "Entity that initiates RAS API actions"),
            "Status": {"State": "Enabled", "Health": "OK"},
            "InitiatorType": data.get("InitiatorType", "BMC"),
            "SupportedActions": data.get("SupportedActions", ["SubmitCPAD", "CollectCPER"]),
            "SupportedEndpoints": data.get("SupportedEndpoints", []),
            "CPAD": {
                "Urgency": data.get("Urgency", 1),
                "Confidence": data.get("Confidence", 90),
                "PlatformID": data.get("PlatformId", "Platform-Default"),
                "PartitionID": data.get("PartitionId", "Default-Partition"),
                "CreatorID": data.get("CreatorId", f"Creator-{initiator_id}"),
                "NotificationType": data.get("NotificationType", "DefaultNotification"),
                "RecordID": f"CPAD-{initiator_id}",
                "SectionCount": 0,
                "Sections": []
            }
        }
        
        self.initiators[initiator_id] = new_initiator
        self.logger.info(f"Created RAS initiator {initiator_id}")
        
        return 201, {"Location": f"/redfish/v1/RASService/Initiators/{initiator_id}"}, new_initiator