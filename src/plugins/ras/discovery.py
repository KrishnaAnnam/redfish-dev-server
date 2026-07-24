"""
RAS discovery resources.

The RAS feature is a plugin-provided extension to the BMC simulator, so the
plugin serves its whole discovery tree dynamically (no static mockup files):

    /redfish/v1/Oem/OCPRASAPIWS/RASService                       -> ras_service()
    /redfish/v1/Oem/OCPRASAPIWS/RASService/RASEndpoints          -> endpoint_collection()
    /redfish/v1/Oem/OCPRASAPIWS/RASService/RASEndpoints/{Id}     -> endpoint(Id)
    /redfish/v1/Oem/OCPRASAPIWS/RASService/SubmitCPADActionInfo  -> submit_cpad_action_info()

Every method returns an ``(http_status, body)`` tuple, matching the signature
the plugin provider uses for GET handling.

Resource shapes follow the OCP RAS API Redfish Specification v0.7.
"""

from typing import Any, Dict, List, Tuple

# Root of the RAS discovery tree (service-root OEM namespace).
RAS_SERVICE_URI = "/redfish/v1/Oem/OCPRASAPIWS/RASService"

# Version of the OCP RAS API surfaced by this service.
RAS_API_VERSION = "1.0.0"

# Platform (node) identifier for this RAS service instance.  This is the same
# GUID that appears as PlatformID in the CPERs/CPADs this platform emits, which
# lets a client map a Redfish host to the PlatformID it reports.  Exposing it on
# RASService is a demo/OEM extension beyond the required properties in spec
# §3.3.1.
PLATFORM_ID = "990f8820-bd4d-5064-58cc-961a053dea79"

# Manager that hosts the CPER LogService where SubmitCPAD writes records.
DEFAULT_MANAGER_ID = "System"


class RASDiscoveryHandler:
    """Serves the read-only RAS service, endpoints, and SubmitCPAD ActionInfo."""

    # RAS endpoint inventory: one entry per RAS-capable hardware source.
    # This demo exposes a single Contoso CPU socket; add dicts to expose more.
    ENDPOINTS: List[Dict[str, Any]] = [
        {
            "Id": "Endpoint-1",
            "Name": "Contoso CPU Socket 0 RAS Endpoint",
            "Description": "RAS API-capable endpoint for Contoso CPU socket 0",
            "EndpointType": "Processor",
            "PartitionID": "22222222-3333-4444-5555-666666666666",
            "CreatorID": "11111111-2222-3333-4444-555555555555",
            "FRUID": "75824856-bd36-2cc8-61f4-39bb3276da2a",
            "FRUText": "Contoso CPU Socket 0",
            "SupportedQueues": [
                "Fatal",
                "Recoverable",
                "Corrected",
                "Informational",
                "PlatformActionStatus",
            ],
        }
    ]

    def __init__(self, manager_id: str = DEFAULT_MANAGER_ID):
        self.manager_id = manager_id

    def ras_service(self) -> Tuple[int, Dict[str, Any]]:
        """Return the top-level RASService resource."""
        return 200, {
            "@odata.type": "#OCPRASService.v1_0_0.RASService",
            "@odata.id": RAS_SERVICE_URI,
            "Id": "RASService",
            "Name": "OCP RAS Service",
            "Description": "OCP RAS API implementation over Redfish",
            "RASAPIVersion": RAS_API_VERSION,
            "PlatformID": PLATFORM_ID,
            "ServiceEnabled": True,
            "Status": {"State": "Enabled", "Health": "OK"},
            "Links": {
                "RASEndpoints": {
                    "@odata.id": f"{RAS_SERVICE_URI}/RASEndpoints"
                },
                "CPERLogService": {
                    "@odata.id": f"/redfish/v1/Managers/{self.manager_id}/LogServices/CPER"
                },
                "EventService": {
                    "@odata.id": "/redfish/v1/EventService"
                },
            },
            "Actions": {
                "#RASService.SubmitCPAD": {
                    "target": f"{RAS_SERVICE_URI}/Actions/RASService.SubmitCPAD",
                    "@Redfish.ActionInfo": f"{RAS_SERVICE_URI}/SubmitCPADActionInfo",
                }
            },
        }

    def endpoint_collection(self) -> Tuple[int, Dict[str, Any]]:
        """Return the collection of RAS endpoints."""
        members = [
            {"@odata.id": f"{RAS_SERVICE_URI}/RASEndpoints/{ep['Id']}"}
            for ep in self.ENDPOINTS
        ]
        return 200, {
            "@odata.type": "#OCPRASEndpointCollection.OCPRASEndpointCollection",
            "@odata.id": f"{RAS_SERVICE_URI}/RASEndpoints",
            "Name": "RAS Endpoint Collection",
            "Description": "Collection of RAS API-capable endpoints",
            "Members@odata.count": len(members),
            "Members": members,
        }

    def endpoint(self, endpoint_id: str) -> Tuple[int, Dict[str, Any]]:
        """Return a single RAS endpoint, or 404 if it is not in the inventory."""
        source = next(
            (ep for ep in self.ENDPOINTS if ep["Id"] == endpoint_id), None
        )
        if source is None:
            return 404, _not_found(f"RAS endpoint '{endpoint_id}' was not found.")

        return 200, {
            "@odata.type": "#OCPRASEndpoint.v1_0_0.RASEndpoint",
            "@odata.id": f"{RAS_SERVICE_URI}/RASEndpoints/{endpoint_id}",
            **source,
            "Status": {"State": "Enabled", "Health": "OK"},
        }

    def submit_cpad_action_info(self) -> Tuple[int, Dict[str, Any]]:
        """Return the ActionInfo describing the SubmitCPAD action parameters."""
        return 200, {
            "@odata.type": "#ActionInfo.v1_2_0.ActionInfo",
            "@odata.id": f"{RAS_SERVICE_URI}/SubmitCPADActionInfo",
            "Id": "SubmitCPADActionInfo",
            "Name": "SubmitCPAD Action Info",
            "Description": (
                "Action information for submitting a CPAD (Common Platform "
                "Action Descriptor) to the OCP RAS Service"
            ),
            "Parameters": [
                {
                    "Name": "CPADData",
                    "Required": True,
                    "DataType": "String",
                    "AllowableValues": [],
                },
                {
                    "Name": "EncodingType",
                    "Required": True,
                    "DataType": "String",
                    "AllowableValues": ["Base64"],
                },
            ],
        }

    def service_root_extension(self) -> Dict[str, Any]:
        """Return the ServiceRoot.Oem.OCPRASAPIWS block that points here.

        The ServiceRoot itself is a static resource; this documents the link it
        must advertise so clients can discover the plugin-served RAS service.
        """
        return {
            "@odata.type": "#OCPRASServiceRoot.v1_0_0.ServiceRootExtension",
            "RASService": {"@odata.id": RAS_SERVICE_URI},
        }


def _not_found(message: str) -> Dict[str, Any]:
    """Build a Redfish ResourceNotFound error body."""
    return {
        "error": {
            "@Message.ExtendedInfo": [
                {
                    "MessageId": "Base.1.16.0.ResourceNotFound",
                    "Message": message,
                    "Severity": "Warning",
                    "Resolution": "Verify the resource identifier and resubmit the request.",
                }
            ]
        }
    }
