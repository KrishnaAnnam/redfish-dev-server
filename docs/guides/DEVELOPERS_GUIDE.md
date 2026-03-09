# BMC Redfish Simulator - Comprehensive Developer's Guide

**Project:** bmc-redfish-simulator  
**Version:** 2.0.0  
**Last Updated:** November 5, 2025  
**Based on:** DMTF Redfish-Mockup-Server

---

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Getting Started](#getting-started)
4. [Core Components](#core-components)
5. [Service Layer](#service-layer)
6. [Handler System](#handler-system)
7. [Enhanced Features](#enhanced-features)
8. [Client Library Development](#client-library-development)
9. [Plugin Development](#plugin-development)
10. [Platform Framework](#platform-framework)
11. [Testing & Validation](#testing--validation)
12. [Best Practices](#best-practices)
13. [API Reference](#api-reference)
14. [Troubleshooting](#troubleshooting)

---

## Introduction

### What is the BMC Redfish Simulator?

The BMC Redfish Simulator (bmc-redfish-simulator) is a comprehensive Redfish API simulator server built upon the DMTF Redfish-Mockup-Server foundation. It enables developers to:

- **Test Redfish Clients**: Develop and test Redfish client applications without physical hardware
- **Simulate BMC Behavior**: Emulate real BMC responses, events, and state changes
- **Prototype Features**: Rapidly prototype new Redfish features and extensions
- **Training & Education**: Learn Redfish API concepts in a safe, controlled environment
- **CI/CD Integration**: Automated testing of Redfish-based management applications

### Key Features

- ✅ **Full Redfish API Support**: Complete implementation of DMTF Redfish standard
- ✅ **Enhanced Message System**: Standardized error responses with ExtendedInfo
- ✅ **Comprehensive Logging**: Event, Audit, and Security logs with persistence
- ✅ **Event System**: Real-time event generation and subscription management
- ✅ **Modular Architecture**: Extensible plugin-based design
- ✅ **Platform Framework**: Support for multiple BMC platform configurations
- ✅ **Client Library**: Ready-to-use Python client for BMC interaction
- ✅ **Web Dashboard**: Browser-based monitoring and control interface

### Who Should Use This Guide?

- **Redfish Client Developers**: Building applications that interact with BMC systems
- **BMC Firmware Engineers**: Testing and validating BMC implementations
- **DevOps Engineers**: Integrating BMC management into automation workflows
- **System Architects**: Designing management solutions for data center infrastructure
- **QA Engineers**: Testing BMC functionality and compliance

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Applications                      │
│  (Web Dashboard, CLI Tools, Monitoring Clients, etc.)       │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/HTTPS (Redfish API)
┌────────────────────▼────────────────────────────────────────┐
│                   HTTP Server Layer                          │
│  • Request Routing      • Session Management                 │
│  • Authentication       • Error Handling                     │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   Handler Layer                              │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │   GET    │  POST    │  PATCH   │   PUT    │  DELETE  │  │
│  │ Handler  │ Handler  │ Handler  │ Handler  │ Handler  │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   Service Layer                              │
│  ┌─────────────┬──────────────┬──────────────┬──────────┐  │
│  │  Message    │   Log        │   Event      │  Session │  │
│  │  Service    │   Service    │   Service    │  Service │  │
│  └─────────────┴──────────────┴──────────────┴──────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│                   Data Layer                                 │
│  • Mockup Files (JSON)  • Log Storage  • State Management   │
│  • Event Queue          • Session Data  • Configuration     │
└─────────────────────────────────────────────────────────────┘
```

### Directory Structure

```
bmc-redfish-simulator/
├── src/                          # Main source code
│   ├── core/                     # Core server components
│   │   ├── __init__.py
│   │   ├── config.py            # Configuration management
│   │   └── mockup_loader.py     # Mockup data loading
│   │
│   ├── handlers/                 # HTTP request handlers
│   │   ├── __init__.py
│   │   ├── base_handler.py      # Base handler class
│   │   ├── get_handler.py       # GET request handling
│   │   ├── post_handler.py      # POST request handling
│   │   ├── patch_handler.py     # PATCH request handling
│   │   ├── put_handler.py       # PUT request handling
│   │   ├── delete_handler.py    # DELETE request handling
│   │   ├── enhanced_handlers.py # Enhanced response handlers
│   │   └── main_handler.py      # Main request router
│   │
│   ├── services/                 # Service layer
│   │   ├── __init__.py
│   │   ├── message_service.py   # Message/error handling
│   │   ├── log_service.py       # Logging system
│   │   ├── event_service.py     # Event management
│   │   └── session_service.py   # Session handling
│   │
│   ├── models/                   # Data models
│   │   ├── __init__.py
│   │   ├── log_entry.py         # Log entry models
│   │   ├── event_record.py      # Event models
│   │   └── subscription.py      # Subscription models
│   │
│   ├── plugins/                  # Plugin system
│   │   ├── __init__.py
│   │   └── plugin_base.py       # Plugin base classes
│   │
│   ├── platform_framework/       # Platform support
│   │   ├── __init__.py
│   │   ├── platform_base.py     # Platform base class
│   │   └── platform_manager.py  # Platform management
│   │
│   └── utils/                    # Utility functions
│       ├── __init__.py
│       ├── file_utils.py        # File operations
│       └── response_utils.py    # Response formatting
│
├── redfish_client/               # Client library
│   ├── __init__.py
│   ├── client.py                # Core client
│   ├── monitoring.py            # Monitoring client
│   ├── README.md
│   ├── examples/                # Usage examples
│   │   ├── __init__.py
│   │   └── basic_examples.py
│   ├── tests/                   # Test suite
│   │   ├── __init__.py
│   │   ├── basic_test.py
│   │   └── test_suite.py
│   └── tools/                   # Utility tools
│       ├── __init__.py
│       ├── web_dashboard.py
│       └── launcher.py
│
├── platforms/                    # Platform configurations
│   ├── default/                 # Default platform
│   └── custom/                  # Custom platforms
│
├── public-rackmount1/           # Sample mockup data
│   ├── redfish/
│   │   └── v1/
│   │       ├── index.json
│   │       ├── Systems/
│   │       ├── Chassis/
│   │       ├── Managers/
│   │       └── ...
│   └── ...
│
├── examples/                     # Example scripts
│   ├── basic_usage.py
│   ├── advanced_features.py
│   └── platform_demo.py
│
├── redfishMockupServer.py       # Main server (original)
├── redfishMockupServer_enhanced.py  # Enhanced server
├── redfishMockupServer_modular.py   # Modular server
├── redfishMockupServer_platform.py  # Platform server
├── redfish_client_launcher.py   # Client demo launcher
│
├── requirements.txt             # Python dependencies
├── requirements_modular.txt     # Modular server deps
├── Dockerfile                   # Docker configuration
│
└── Documentation/
    ├── DEVELOPERS_GUIDE.md      # This file
    ├── README.md                # General readme
    ├── QUICK_START.md           # Quick start guide
    ├── PLATFORM_DEVELOPMENT.md  # Platform development
    └── MIGRATION_GUIDE.md       # Migration guide
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **HTTP Server** | Request routing, SSL/TLS, session management |
| **Handlers** | HTTP method processing, request validation |
| **Services** | Business logic, data processing, state management |
| **Models** | Data structures, validation, serialization |
| **Plugins** | Extensibility, custom behavior injection |
| **Platform Framework** | Multi-platform support, configuration management |
| **Client Library** | BMC interaction, monitoring, testing |

---

## Getting Started

### Prerequisites

#### Required Software
```bash
# Python 3.7 or higher
python3 --version

# pip package manager
pip3 --version

# git (for cloning repository)
git --version
```

#### Python Dependencies
```bash
# Install core dependencies
pip install -r requirements.txt

# For modular server
pip install -r requirements_modular.txt

# For web dashboard
pip install flask

# For development
pip install pytest pytest-cov black flake8
```

### Installation

#### Clone the Repository
```bash
git clone <repository-url>/bmc-redfish-simulator.git
cd bmc-redfish-simulator
```

> **Note:** This project is based on the DMTF Redfish-Mockup-Server but has been extended with comprehensive BMC simulation capabilities.

#### Basic Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Verify installation
python3 redfishMockupServer.py --help
```

#### Development Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-cov black flake8
```

### Quick Start

#### Run Basic Server
```bash
# Start server with default mockup
python3 redfishMockupServer.py

# Start with custom mockup
python3 redfishMockupServer.py -D /path/to/mockup -p 8000

# Start with SSL
python3 redfishMockupServer.py --ssl --cert server.crt --key server.key
```

#### Run Enhanced Server
```bash
# Start enhanced server with all features
python3 redfishMockupServer_enhanced.py -D public-rackmount1 -p 8000

# With enhanced responses enabled
python3 redfishMockupServer_enhanced.py --enhanced-responses
```

#### Run Demo Scripts
```bash
# Quick feature demo
python3 quick_enhanced_demo.py

# Comprehensive system demo
python3 demo_enhanced_redfish_system.py

# Complete BMC simulator showcase
python3 bmc_simulator_demo.py
```

#### Test Client Library
```bash
# Run basic client test
python3 redfish_client/tests/basic_test.py

# Run full test suite
python3 redfish_client/tests/test_suite.py

# Launch interactive demo
python3 redfish_client_launcher.py
```

### First API Call

```bash
# Using curl
curl http://localhost:8000/redfish/v1

# Expected response
{
  "@odata.context": "/redfish/v1/$metadata#ServiceRoot.ServiceRoot",
  "@odata.id": "/redfish/v1",
  "@odata.type": "#ServiceRoot.v1_5_0.ServiceRoot",
  "Id": "RootService",
  "Name": "Root Service",
  "RedfishVersion": "1.6.0",
  "UUID": "92384634-2938-2342-8820-489239905423",
  "Systems": {
    "@odata.id": "/redfish/v1/Systems"
  },
  "Chassis": {
    "@odata.id": "/redfish/v1/Chassis"
  },
  "Managers": {
    "@odata.id": "/redfish/v1/Managers"
  }
}
```

---

## Core Components

### Configuration System

#### Configuration File (`src/core/config.py`)

```python
class ServerConfig:
    """Server configuration management"""
    
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 8000
        self.mockup_dir = "public-rackmount1"
        self.ssl_enabled = False
        self.cert_file = None
        self.key_file = None
        self.enhanced_responses = True
        self.logging_enabled = True
        self.event_service_enabled = True
        
    def load_from_file(self, config_file):
        """Load configuration from JSON file"""
        with open(config_file, 'r') as f:
            config_data = json.load(f)
            self.__dict__.update(config_data)
    
    def to_dict(self):
        """Convert to dictionary"""
        return self.__dict__.copy()
```

#### Usage Example

```python
from src.core.config import ServerConfig

# Create configuration
config = ServerConfig()
config.host = "0.0.0.0"
config.port = 8443
config.ssl_enabled = True
config.cert_file = "server.crt"
config.key_file = "server.key"

# Or load from file
config.load_from_file("config.json")
```

### Mockup Loader

The mockup loader is responsible for reading and parsing Redfish mockup data from the filesystem.

#### Key Functions

```python
def load_mockup(mockup_dir: str) -> Dict[str, Any]:
    """
    Load mockup data from directory
    
    Args:
        mockup_dir: Path to mockup directory
        
    Returns:
        Dictionary containing mockup data
    """
    pass

def get_resource(path: str) -> Dict[str, Any]:
    """
    Get specific resource from mockup
    
    Args:
        path: Resource path (e.g., /redfish/v1/Systems/1)
        
    Returns:
        Resource data as dictionary
    """
    pass

def update_resource(path: str, data: Dict[str, Any]) -> bool:
    """
    Update resource in mockup
    
    Args:
        path: Resource path
        data: Updated resource data
        
    Returns:
        True if successful
    """
    pass
```

### Session Management

#### Session Service (`src/services/session_service.py`)

```python
class SessionService:
    """Manages Redfish sessions"""
    
    def __init__(self):
        self.sessions = {}
        self.session_timeout = 600  # 10 minutes
    
    def create_session(self, username: str, password: str) -> Optional[str]:
        """
        Create new session
        
        Args:
            username: User name
            password: User password
            
        Returns:
            Session token or None
        """
        # Validate credentials
        if not self._validate_credentials(username, password):
            return None
        
        # Generate session token
        session_token = self._generate_token()
        
        # Store session
        self.sessions[session_token] = {
            "username": username,
            "created": time.time(),
            "last_access": time.time()
        }
        
        return session_token
    
    def validate_session(self, session_token: str) -> bool:
        """Validate session token"""
        if session_token not in self.sessions:
            return False
        
        session = self.sessions[session_token]
        
        # Check timeout
        if time.time() - session["last_access"] > self.session_timeout:
            del self.sessions[session_token]
            return False
        
        # Update last access
        session["last_access"] = time.time()
        return True
    
    def delete_session(self, session_token: str) -> bool:
        """Delete session"""
        if session_token in self.sessions:
            del self.sessions[session_token]
            return True
        return False
```

---

## Service Layer

### Message Service

The Message Service provides standardized Redfish message responses with proper ExtendedInfo formatting.

#### Core Features

- **Message Registry Support**: DMTF Base Registry 1.5.0
- **Dynamic Message Formatting**: Template-based message generation with arguments
- **Severity Levels**: OK, Warning, Critical
- **Related Properties**: Link messages to specific resource properties
- **Extensibility**: Support for custom message registries

#### Usage Example

```python
from src.services.message_service import MessageService, RedfishMessage

# Initialize service
msg_service = MessageService()

# Create success message
success_msg = msg_service.create_message(
    "Base.1.5.0.Success",
    []
)

# Create error message with arguments
error_msg = msg_service.create_message(
    "Base.1.5.0.PropertyValueTypeError",
    ["true", "Enabled"],  # value, property name
    related_properties=["Enabled"]
)

# Generate complete response
response = msg_service.create_error_response(
    404,
    "ResourceNotFound",
    ["/redfish/v1/Systems/Invalid"]
)
```

#### Message Registry Structure

```json
{
  "Success": {
    "Message": "Successfully Completed Request",
    "Severity": "OK",
    "NumberOfArgs": 0,
    "Resolution": "None"
  },
  "PropertyValueTypeError": {
    "Message": "The value %1 for the property %2 is of a different type than the property can accept.",
    "Severity": "Warning",
    "NumberOfArgs": 2,
    "Resolution": "Correct the value for the property in the request body and resubmit the request if the operation failed."
  }
}
```

### Log Service

Comprehensive logging system with multiple log types and persistent storage.

#### Log Types

1. **Event Log**: System events and state changes
2. **Audit Log**: User actions and administrative operations
3. **Security Log**: Authentication attempts and security events

#### Log Entry Structure

```python
class LogEntry:
    """Represents a single log entry"""
    
    def __init__(self, entry_type: str, severity: str, message: str):
        self.id = self._generate_id()
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.entry_type = entry_type
        self.severity = severity
        self.message = message
        self.sensor_type = None
        self.sensor_number = None
        self.message_id = None
        self.message_args = []
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Redfish LogEntry format"""
        return {
            "@odata.id": f"/redfish/v1/Managers/BMC/LogServices/{self.entry_type}/Entries/{self.id}",
            "@odata.type": "#LogEntry.v1_4_0.LogEntry",
            "Id": self.id,
            "Name": f"{self.entry_type} Log Entry",
            "EntryType": "Event",
            "Created": self.timestamp,
            "Severity": self.severity,
            "Message": self.message,
            "MessageId": self.message_id,
            "MessageArgs": self.message_args
        }
```

#### Usage Example

```python
from src.services.log_service import LogService

# Initialize service
log_service = LogService()

# Create event log entry
log_service.create_log_entry(
    "Event",
    "Warning",
    "System temperature exceeded threshold",
    message_id="Base.1.5.0.TempExceedsWarningThreshold",
    message_args=["CPU1", "85", "80"]
)

# Create audit log entry
log_service.create_audit_entry(
    "admin",
    "PATCH",
    "/redfish/v1/Systems/1",
    {"Boot": {"BootSourceOverrideEnabled": "Once"}},
    success=True
)

# Retrieve log entries
entries = log_service.get_log_entries("Event", limit=10)

# Clear log
log_service.clear_log("Event")
```

### Event Service

Real-time event generation and subscription management.

#### Event Types

- **StatusChange**: Resource status changes
- **ResourceUpdated**: Resource modifications
- **ResourceAdded**: New resources created
- **ResourceRemoved**: Resources deleted
- **Alert**: System alerts and warnings

#### Subscription Management

```python
from src.services.event_service import EventService

# Initialize service
event_service = EventService()

# Create subscription
subscription_id = event_service.create_subscription(
    destination="https://listener.example.com/events",
    context="MyApp",
    protocol="Redfish",
    event_types=["Alert", "StatusChange"],
    resource_types=["ComputerSystem", "Chassis"]
)

# Send event
event_service.send_event(
    event_type="Alert",
    message_id="Base.1.5.0.TempExceedsWarningThreshold",
    message_args=["CPU1", "85", "80"],
    origin_of_condition="/redfish/v1/Systems/1",
    severity="Warning"
)

# Delete subscription
event_service.delete_subscription(subscription_id)
```

#### Event Delivery

Events are delivered asynchronously to subscribed endpoints:

```json
{
  "@odata.type": "#Event.v1_3_0.Event",
  "Id": "1",
  "Name": "Event Array",
  "Context": "MyApp",
  "Events": [
    {
      "EventType": "Alert",
      "EventId": "1234567890",
      "EventTimestamp": "2025-11-05T10:30:00Z",
      "Severity": "Warning",
      "Message": "Temperature for CPU1 of 85 degrees C exceeds warning threshold of 80 degrees C.",
      "MessageId": "Base.1.5.0.TempExceedsWarningThreshold",
      "MessageArgs": ["CPU1", "85", "80"],
      "OriginOfCondition": {
        "@odata.id": "/redfish/v1/Systems/1"
      }
    }
  ]
}
```

---

## Handler System

### Base Handler

All HTTP handlers inherit from `BaseRedfishHandler`, which provides common functionality:

```python
class BaseRedfishHandler(BaseHTTPRequestHandler):
    """Base class for all Redfish request handlers"""
    
    def __init__(self, request, client_address, server):
        self.config = server.config
        self.mockup_loader = server.mockup_loader
        self.message_service = server.message_service
        self.log_service = server.log_service
        self.event_service = server.event_service
        self.session_service = server.session_service
        
        super().__init__(request, client_address, server)
    
    def send_response_with_message(self, code: int, message_id: str, 
                                   message_args: List[str] = None,
                                   additional_data: Dict[str, Any] = None):
        """Send response with Redfish message"""
        # Generate message
        message = self.message_service.create_message(
            message_id, message_args or []
        )
        
        # Build response
        response_data = {
            "@odata.type": "#Message.v1_0_0.Message",
            "MessageId": message.message_id,
            "Message": message.message,
            "Severity": message.severity,
            "Resolution": message.resolution
        }
        
        if additional_data:
            response_data.update(additional_data)
        
        # Send response
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data, indent=2).encode())
    
    def authenticate(self) -> bool:
        """Authenticate request"""
        # Check for session token
        session_token = self.headers.get('X-Auth-Token')
        if session_token:
            return self.session_service.validate_session(session_token)
        
        # Check for basic auth
        auth_header = self.headers.get('Authorization')
        if auth_header and auth_header.startswith('Basic '):
            # Validate basic auth
            return self._validate_basic_auth(auth_header)
        
        return False
```

### GET Handler

Handles resource retrieval with support for query parameters:

```python
class GetHandler(BaseRedfishHandler):
    """Handle GET requests"""
    
    def do_GET(self):
        """Process GET request"""
        # Parse URL and query parameters
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        
        # Handle special endpoints
        if path == "/redfish":
            self._handle_redfish_root()
            return
        
        if path == "/redfish/v1/$metadata":
            self._handle_metadata()
            return
        
        # Get resource from mockup
        resource = self.mockup_loader.get_resource(path)
        
        if not resource:
            self.send_response_with_message(
                404,
                "Base.1.5.0.ResourceNotFound",
                [path]
            )
            return
        
        # Handle query parameters
        if "$expand" in query:
            resource = self._handle_expand(resource, query["$expand"][0])
        
        if "$select" in query:
            resource = self._handle_select(resource, query["$select"][0])
        
        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('OData-Version', '4.0')
        self.end_headers()
        self.wfile.write(json.dumps(resource, indent=2).encode())
    
    def _handle_expand(self, resource: Dict, expand_param: str) -> Dict:
        """Handle $expand query parameter"""
        # Implementation for expanding related resources
        pass
    
    def _handle_select(self, resource: Dict, select_param: str) -> Dict:
        """Handle $select query parameter"""
        # Implementation for selecting specific properties
        pass
```

### POST Handler

Handles resource creation and actions:

```python
class PostHandler(BaseRedfishHandler):
    """Handle POST requests"""
    
    def do_POST(self):
        """Process POST request"""
        # Authenticate
        if not self.authenticate():
            self.send_response_with_message(
                401,
                "Base.1.5.0.NoValidSession"
            )
            return
        
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self.send_response_with_message(
                400,
                "Base.1.5.0.MalformedJSON"
            )
            return
        
        # Determine request type
        if self.path.endswith("/Actions"):
            self._handle_action(data)
        elif "EventService/Subscriptions" in self.path:
            self._handle_subscription(data)
        else:
            self._handle_resource_creation(data)
    
    def _handle_action(self, data: Dict):
        """Handle Redfish action"""
        # Extract action name
        action_name = data.get("#Action", "")
        
        # Validate action
        if not action_name:
            self.send_response_with_message(
                400,
                "Base.1.5.0.ActionParameterMissing",
                ["#Action"]
            )
            return
        
        # Process action
        result = self._process_action(action_name, data)
        
        # Generate event
        self.event_service.send_event(
            event_type="Alert",
            message_id="Base.1.5.0.ActionCompleted",
            message_args=[action_name],
            origin_of_condition=self.path,
            severity="OK"
        )
        
        # Create audit log
        self.log_service.create_audit_entry(
            username="admin",
            operation="POST",
            resource_path=self.path,
            request_data=data,
            success=True
        )
        
        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result, indent=2).encode())
    
    def _handle_resource_creation(self, data: Dict):
        """Handle resource creation"""
        # Validate data
        errors = self._validate_create_data(data)
        if errors:
            self.send_response_with_message(
                400,
                "Base.1.5.0.CreateFailedMissingReqProperties",
                errors
            )
            return
        
        # Create resource
        new_id = self._generate_resource_id()
        resource_path = f"{self.path}/{new_id}"
        
        # Save resource
        self.mockup_loader.create_resource(resource_path, data)
        
        # Generate event
        self.event_service.send_event(
            event_type="ResourceAdded",
            message_id="Base.1.5.0.ResourceCreated",
            message_args=[resource_path],
            origin_of_condition=resource_path,
            severity="OK"
        )
        
        # Send response
        self.send_response(201)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Location', resource_path)
        self.end_headers()
        
        response_data = {
            "@odata.id": resource_path,
            "@odata.type": data.get("@odata.type", ""),
            "Id": new_id,
            **data
        }
        
        self.wfile.write(json.dumps(response_data, indent=2).encode())
```

### PATCH Handler

Handles resource updates:

```python
class PatchHandler(BaseRedfishHandler):
    """Handle PATCH requests"""
    
    def do_PATCH(self):
        """Process PATCH request"""
        # Authenticate
        if not self.authenticate():
            self.send_response_with_message(
                401,
                "Base.1.5.0.NoValidSession"
            )
            return
        
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        try:
            patch_data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self.send_response_with_message(
                400,
                "Base.1.5.0.MalformedJSON"
            )
            return
        
        # Get existing resource
        resource = self.mockup_loader.get_resource(self.path)
        if not resource:
            self.send_response_with_message(
                404,
                "Base.1.5.0.ResourceNotFound",
                [self.path]
            )
            return
        
        # Validate patch data
        errors, warnings = self._validate_patch_data(patch_data, resource)
        
        # Track changes
        changes = {}
        
        # Apply updates
        for key, value in patch_data.items():
            if key.startswith("@odata"):
                continue
            
            if key not in resource:
                warnings.append(self.message_service.create_message(
                    "Base.1.5.0.PropertyUnknown",
                    [key]
                ))
                continue
            
            old_value = resource.get(key)
            if old_value != value:
                changes[key] = {"old": old_value, "new": value}
                resource[key] = value
        
        # Save updated resource
        self.mockup_loader.update_resource(self.path, resource)
        
        # Generate event
        if changes:
            self.event_service.send_event(
                event_type="ResourceUpdated",
                message_id="Base.1.5.0.ResourceModified",
                message_args=[self.path],
                origin_of_condition=self.path,
                severity="OK"
            )
        
        # Create audit log
        self.log_service.create_audit_entry(
            username="admin",
            operation="PATCH",
            resource_path=self.path,
            request_data=patch_data,
            changes=changes,
            success=True
        )
        
        # Build response
        response_data = resource.copy()
        
        if warnings:
            response_data["@Message.ExtendedInfo"] = [
                w.to_dict() for w in warnings
            ]
        
        # Send response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data, indent=2).encode())
```

---

## Enhanced Features

### Enhanced Response System

The enhanced response system provides standardized error handling and message formatting:

#### Key Features

1. **Automatic ExtendedInfo**: All responses include detailed message information
2. **Error Context**: Errors include related properties and resolution steps
3. **Consistent Formatting**: Uniform response structure across all endpoints
4. **Multi-Message Support**: Single response can contain multiple messages

#### Implementation

```python
class EnhancedResponseMixin:
    """Mixin for enhanced response handling"""
    
    def create_enhanced_response(self, 
                                 status_code: int,
                                 data: Dict[str, Any] = None,
                                 messages: List[RedfishMessage] = None,
                                 headers: Dict[str, str] = None) -> Tuple[int, Dict, Dict]:
        """
        Create enhanced response with messages
        
        Args:
            status_code: HTTP status code
            data: Response data
            messages: List of Redfish messages
            headers: Additional headers
            
        Returns:
            Tuple of (status_code, headers, body)
        """
        response_data = data or {}
        response_headers = headers or {}
        
        # Add standard headers
        response_headers['Content-Type'] = 'application/json'
        response_headers['OData-Version'] = '4.0'
        
        # Add messages if present
        if messages:
            response_data['@Message.ExtendedInfo'] = [
                msg.to_dict() for msg in messages
            ]
        
        return status_code, response_headers, response_data
    
    def create_error_response(self,
                             status_code: int,
                             message_id: str,
                             message_args: List[str] = None,
                             related_properties: List[str] = None) -> Tuple[int, Dict, Dict]:
        """Create standardized error response"""
        message = self.message_service.create_message(
            message_id,
            message_args or [],
            related_properties or []
        )
        
        error_response = {
            "error": {
                "code": message_id.split('.')[-1],
                "message": message.message,
                "@Message.ExtendedInfo": [message.to_dict()]
            }
        }
        
        headers = {
            'Content-Type': 'application/json',
            'OData-Version': '4.0'
        }
        
        return status_code, headers, error_response
```

### Automatic Event Generation

Events are automatically generated for state-changing operations:

```python
def _generate_event_for_operation(self, operation: str, path: str, 
                                  data: Dict = None, success: bool = True):
    """Generate event for CRUD operation"""
    
    event_type_map = {
        "POST": "ResourceAdded",
        "PATCH": "ResourceUpdated",
        "PUT": "ResourceUpdated",
        "DELETE": "ResourceRemoved"
    }
    
    message_id_map = {
        "POST": "Base.1.5.0.ResourceCreated",
        "PATCH": "Base.1.5.0.ResourceModified",
        "PUT": "Base.1.5.0.ResourceModified",
        "DELETE": "Base.1.5.0.ResourceRemoved"
    }
    
    event_type = event_type_map.get(operation, "Alert")
    message_id = message_id_map.get(operation, "Base.1.5.0.GeneralError")
    
    self.event_service.send_event(
        event_type=event_type,
        message_id=message_id,
        message_args=[path],
        origin_of_condition=path,
        severity="OK" if success else "Critical",
        additional_data={"Operation": operation, "Data": data}
    )
```

### Comprehensive Audit Trail

All operations are logged to the audit log:

```python
class AuditLogger:
    """Audit logging for all operations"""
    
    def log_operation(self, 
                     username: str,
                     operation: str,
                     resource_path: str,
                     request_data: Dict = None,
                     changes: Dict = None,
                     success: bool = True,
                     error_message: str = None):
        """Log operation to audit log"""
        
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "username": username,
            "operation": operation,
            "resource": resource_path,
            "success": success,
            "ip_address": self.client_address[0],
            "user_agent": self.headers.get('User-Agent', 'Unknown')
        }
        
        if request_data:
            audit_entry["request"] = request_data
        
        if changes:
            audit_entry["changes"] = changes
        
        if error_message:
            audit_entry["error"] = error_message
        
        # Save to audit log
        self.log_service.create_audit_entry(**audit_entry)
```

---

## Client Library Development

### Core Client

The `RedfishClient` class provides a high-level interface for BMC interaction:

```python
from redfish_client.client import RedfishClient

# Create client
client = RedfishClient(
    base_url="http://localhost:8000",
    username="admin",
    password="password",
    timeout=30,
    verify_ssl=False
)

# Connect to BMC
if client.connect():
    print("Connected successfully")
    
    # Get service root
    root = client.get_service_root()
    print(f"Redfish Version: {root['RedfishVersion']}")
    
    # List systems
    systems = client.get_systems()
    for system_id in systems:
        system = client.get_system(system_id)
        print(f"System: {system['Name']}")
        print(f"  Power State: {system['PowerState']}")
        print(f"  Health: {system['Status']['Health']}")
    
    # Power operations
    client.power_on("1")
    client.power_off("1", force=True)
    client.reset_system("1", reset_type="GracefulRestart")
    
    # Subscribe to events
    subscription_id = client.subscribe_to_events(
        destination="https://listener.example.com/events",
        event_types=["Alert", "StatusChange"]
    )
    
    # Disconnect
    client.disconnect()
```

### Monitoring Client

The `RedfishMonitoringClient` provides advanced monitoring capabilities:

```python
from redfish_client.monitoring import RedfishMonitoringClient

# Create monitoring client
monitor = RedfishMonitoringClient(
    base_url="http://localhost:8000",
    username="admin",
    password="password"
)

# Start monitoring
monitor.start_monitoring(
    duration=300,  # 5 minutes
    interval=5,    # Check every 5 seconds
    alert_threshold=85.0,  # Alert at 85% utilization
    enable_reports=True
)

# Get current metrics
metrics = monitor.get_current_metrics()
print(f"CPU Usage: {metrics.cpu_usage}%")
print(f"Memory Usage: {metrics.memory_usage}%")
print(f"Temperature: {metrics.temperature}°C")
print(f"Health Score: {metrics.health_score}/100")

# Get alerts
alerts = monitor.get_alerts()
for alert in alerts:
    print(f"[{alert.severity}] {alert.message}")

# Generate report
report = monitor.generate_report()
print(report)
```

### Building Custom Clients

#### Example: Custom Firmware Update Client

```python
class FirmwareUpdateClient(RedfishClient):
    """Client for firmware updates"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def get_firmware_inventory(self) -> List[Dict]:
        """Get firmware inventory"""
        url = f"{self.base_url}/redfish/v1/UpdateService/FirmwareInventory"
        response = self._make_request("GET", url)
        
        if response.status_code == 200:
            data = response.json()
            members = data.get("Members", [])
            
            inventory = []
            for member in members:
                fw_url = member["@odata.id"]
                fw_response = self._make_request("GET", f"{self.base_url}{fw_url}")
                if fw_response.status_code == 200:
                    inventory.append(fw_response.json())
            
            return inventory
        
        return []
    
    def upload_firmware(self, firmware_file: str, targets: List[str] = None) -> str:
        """Upload firmware image"""
        url = f"{self.base_url}/redfish/v1/UpdateService"
        
        # Read firmware file
        with open(firmware_file, 'rb') as f:
            firmware_data = f.read()
        
        # Create multipart form data
        files = {
            'file': (firmware_file, firmware_data, 'application/octet-stream')
        }
        
        data = {}
        if targets:
            data['Targets'] = targets
        
        response = self._make_request(
            "POST",
            f"{url}/Actions/UpdateService.SimpleUpdate",
            files=files,
            data=data
        )
        
        if response.status_code == 202:
            # Get task monitor URL
            task_url = response.headers.get('Location')
            return task_url
        
        return None
    
    def monitor_update_task(self, task_url: str) -> Dict:
        """Monitor firmware update task"""
        while True:
            response = self._make_request("GET", f"{self.base_url}{task_url}")
            
            if response.status_code == 200:
                task = response.json()
                state = task.get("TaskState")
                
                if state in ["Completed", "Exception", "Killed"]:
                    return task
                
                print(f"Task state: {state}, {task.get('PercentComplete', 0)}%")
            
            time.sleep(5)

# Usage
fw_client = FirmwareUpdateClient("http://localhost:8000", "admin", "password")
if fw_client.connect():
    # Get current firmware
    inventory = fw_client.get_firmware_inventory()
    for fw in inventory:
        print(f"{fw['Name']}: {fw['Version']}")
    
    # Upload new firmware
    task_url = fw_client.upload_firmware(
        "bmc_firmware_v2.0.bin",
        targets=["/redfish/v1/Managers/BMC"]
    )
    
    if task_url:
        # Monitor update
        result = fw_client.monitor_update_task(task_url)
        print(f"Update result: {result['TaskState']}")
```

---

## Plugin Development

### Plugin Architecture

Plugins allow extending the BMC simulator without modifying core code:

```
plugins/
├── __init__.py
├── plugin_base.py          # Base plugin class
├── thermal_plugin.py       # Example: Thermal monitoring
├── power_plugin.py         # Example: Power management
└── custom_plugin.py        # Your custom plugin
```

### Creating a Plugin

```python
from src.plugins.plugin_base import PluginBase

class CustomPlugin(PluginBase):
    """Example custom plugin"""
    
    def __init__(self, config: Dict = None):
        super().__init__("CustomPlugin", "1.0.0")
        self.config = config or {}
        
    def initialize(self):
        """Initialize plugin"""
        self.logger.info(f"Initializing {self.name} plugin")
        # Perform initialization tasks
        
    def on_request(self, method: str, path: str, data: Dict = None) -> Optional[Dict]:
        """
        Called before request is processed
        
        Args:
            method: HTTP method
            path: Request path
            data: Request data
            
        Returns:
            Modified data or None
        """
        # Intercept and modify requests
        if path.startswith("/redfish/v1/Custom"):
            return self._handle_custom_request(method, path, data)
        
        return None  # Let normal handler process
    
    def on_response(self, method: str, path: str, response: Dict) -> Dict:
        """
        Called before response is sent
        
        Args:
            method: HTTP method
            path: Request path
            response: Response data
            
        Returns:
            Modified response
        """
        # Add custom headers or modify response
        if "CustomData" not in response:
            response["CustomData"] = self._get_custom_data()
        
        return response
    
    def on_event(self, event_type: str, event_data: Dict):
        """
        Called when event is generated
        
        Args:
            event_type: Type of event
            event_data: Event data
        """
        # React to events
        if event_type == "Alert":
            self._process_alert(event_data)
    
    def _handle_custom_request(self, method: str, path: str, data: Dict) -> Dict:
        """Handle custom endpoint"""
        return {
            "Message": "Custom endpoint handled by plugin",
            "Method": method,
            "Path": path
        }
    
    def _get_custom_data(self) -> Dict:
        """Get custom data"""
        return {
            "PluginName": self.name,
            "PluginVersion": self.version,
            "Timestamp": datetime.now().isoformat()
        }
    
    def shutdown(self):
        """Cleanup on shutdown"""
        self.logger.info(f"Shutting down {self.name} plugin")
```

### Registering Plugins

```python
from src.plugins.plugin_manager import PluginManager
from plugins.custom_plugin import CustomPlugin

# Create plugin manager
plugin_manager = PluginManager()

# Register plugins
plugin_manager.register(CustomPlugin(config={"option": "value"}))

# Initialize all plugins
plugin_manager.initialize_all()

# Use in handlers
result = plugin_manager.execute_hook("on_request", method="GET", path="/redfish/v1/Custom")
```

---

## Platform Framework

### Platform Support

The platform framework allows supporting multiple BMC configurations:

```python
from src.platform_framework.platform_base import PlatformBase

class CustomPlatform(PlatformBase):
    """Custom platform implementation"""
    
    def __init__(self):
        super().__init__(
            name="CustomPlatform",
            version="1.0.0",
            description="Custom BMC platform"
        )
        
    def initialize(self, config: Dict):
        """Initialize platform"""
        self.config = config
        self.load_platform_data()
        
    def get_system_info(self) -> Dict:
        """Get platform-specific system information"""
        return {
            "Manufacturer": "Custom Corp",
            "Model": "SuperServer 3000",
            "SerialNumber": "SN123456789",
            "PartNumber": "PN-SS3000-01"
        }
    
    def get_chassis_info(self) -> Dict:
        """Get chassis information"""
        return {
            "ChassisType": "RackMount",
            "PowerState": "On",
            "IndicatorLED": "Off"
        }
    
    def power_control(self, action: str) -> bool:
        """Platform-specific power control"""
        if action == "On":
            return self._power_on()
        elif action == "ForceOff":
            return self._power_off(force=True)
        elif action == "GracefulShutdown":
            return self._power_off(force=False)
        elif action == "ForceRestart":
            return self._reset(force=True)
        
        return False
    
    def get_sensors(self) -> List[Dict]:
        """Get platform sensors"""
        return [
            {
                "Name": "CPU1 Temp",
                "Reading": 65.0,
                "Units": "Celsius",
                "Status": {"Health": "OK"}
            },
            {
                "Name": "System Fan 1",
                "Reading": 5000,
                "Units": "RPM",
                "Status": {"Health": "OK"}
            }
        ]
```

---

## Testing & Validation

### Unit Tests

```python
import unittest
from src.services.message_service import MessageService

class TestMessageService(unittest.TestCase):
    """Test message service functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.service = MessageService()
    
    def test_create_success_message(self):
        """Test success message creation"""
        message = self.service.create_message("Base.1.5.0.Success", [])
        
        self.assertEqual(message.message_id, "Base.1.5.0.Success")
        self.assertEqual(message.severity, "OK")
        self.assertIn("Successfully", message.message)
    
    def test_create_error_message_with_args(self):
        """Test error message with arguments"""
        message = self.service.create_message(
            "Base.1.5.0.PropertyValueTypeError",
            ["true", "Enabled"]
        )
        
        self.assertEqual(message.severity, "Warning")
        self.assertIn("true", message.message)
        self.assertIn("Enabled", message.message)
    
    def test_message_to_dict(self):
        """Test message serialization"""
        message = self.service.create_message("Base.1.5.0.Success", [])
        message_dict = message.to_dict()
        
        self.assertIn("MessageId", message_dict)
        self.assertIn("Message", message_dict)
        self.assertIn("Severity", message_dict)
        self.assertEqual(message_dict["@odata.type"], "#Message.v1_0_0.Message")

if __name__ == '__main__':
    unittest.main()
```

### Integration Tests

```python
import requests
import unittest

class TestBMCIntegration(unittest.TestCase):
    """Integration tests for BMC simulator"""
    
    BASE_URL = "http://localhost:8000"
    
    def test_service_root(self):
        """Test service root endpoint"""
        response = requests.get(f"{self.BASE_URL}/redfish/v1")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("RedfishVersion", data)
        self.assertIn("Systems", data)
    
    def test_system_collection(self):
        """Test systems collection"""
        response = requests.get(f"{self.BASE_URL}/redfish/v1/Systems")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Members", data)
        self.assertGreater(len(data["Members"]), 0)
    
    def test_power_control(self):
        """Test power control action"""
        action_data = {
            "ResetType": "ForceRestart"
        }
        
        response = requests.post(
            f"{self.BASE_URL}/redfish/v1/Systems/1/Actions/ComputerSystem.Reset",
            json=action_data,
            headers={"Content-Type": "application/json"}
        )
        
        self.assertIn(response.status_code, [200, 204])
    
    def test_patch_resource(self):
        """Test resource update"""
        patch_data = {
            "AssetTag": "TestTag123"
        }
        
        response = requests.patch(
            f"{self.BASE_URL}/redfish/v1/Systems/1",
            json=patch_data,
            headers={"Content-Type": "application/json"}
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("AssetTag"), "TestTag123")

if __name__ == '__main__':
    unittest.main()
```

---

## Best Practices

### Code Organization

1. **Separation of Concerns**: Keep handlers, services, and models separate
2. **DRY Principle**: Reuse common code through base classes and utilities
3. **Type Hints**: Use type hints for better code documentation and IDE support
4. **Documentation**: Document all public APIs with docstrings

### Error Handling

```python
def safe_operation(func):
    """Decorator for safe operation execution"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            return None
    return wrapper

@safe_operation
def get_resource(path: str) -> Optional[Dict]:
    """Get resource with error handling"""
    # Implementation
    pass
```

### Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bmc_simulator.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Use throughout code
logger.info("Server started")
logger.warning("Resource not found")
logger.error("Failed to process request")
logger.debug("Debug information")
```

### Performance

1. **Caching**: Cache frequently accessed resources
2. **Async Operations**: Use background threads for long-running tasks
3. **Connection Pooling**: Reuse HTTP connections
4. **Resource Limits**: Set appropriate timeouts and size limits

---

## API Reference

### Core Classes

#### RedfishClient

```python
class RedfishClient:
    """Core Redfish client for BMC interaction"""
    
    def __init__(self, base_url: str, username: str, password: str, 
                 timeout: int = 30, verify_ssl: bool = True)
    
    def connect(self) -> bool:
        """Connect to BMC and create session"""
    
    def disconnect(self) -> bool:
        """Disconnect and close session"""
    
    def get_service_root(self) -> Dict[str, Any]:
        """Get service root"""
    
    def get_systems(self) -> List[str]:
        """Get list of system IDs"""
    
    def get_system(self, system_id: str) -> Dict[str, Any]:
        """Get system details"""
    
    def power_on(self, system_id: str) -> bool:
        """Power on system"""
    
    def power_off(self, system_id: str, force: bool = False) -> bool:
        """Power off system"""
    
    def reset_system(self, system_id: str, reset_type: str = "GracefulRestart") -> bool:
        """Reset system"""
    
    def subscribe_to_events(self, destination: str, 
                           event_types: List[str] = None) -> str:
        """Subscribe to events"""
```

#### MessageService

```python
class MessageService:
    """Redfish message service"""
    
    def create_message(self, message_id: str, message_args: List[str],
                      related_properties: List[str] = None) -> RedfishMessage:
        """Create Redfish message"""
    
    def create_error_response(self, status_code: int, message_id: str,
                             message_args: List[str] = None) -> Dict:
        """Create error response"""
```

#### LogService

```python
class LogService:
    """Comprehensive logging service"""
    
    def create_log_entry(self, log_type: str, severity: str, message: str,
                        message_id: str = None, message_args: List = None) -> str:
        """Create log entry"""
    
    def get_log_entries(self, log_type: str, limit: int = None) -> List[Dict]:
        """Get log entries"""
    
    def clear_log(self, log_type: str) -> bool:
        """Clear log"""
```

---

## Troubleshooting

### Common Issues

#### Server Won't Start

**Problem**: Server fails to start  
**Solutions**:
- Check if port is already in use: `netstat -an | grep 8000`
- Verify Python version: `python3 --version`
- Check dependencies: `pip list`
- Review error logs: `tail -f bmc_simulator.log`

#### Connection Refused

**Problem**: Client can't connect to server  
**Solutions**:
- Verify server is running: `ps aux | grep redfishMockupServer`
- Check firewall settings
- Verify correct host and port
- Test with curl: `curl http://localhost:8000/redfish/v1`

#### SSL/TLS Issues

**Problem**: SSL certificate errors  
**Solutions**:
- Verify certificate files exist
- Check certificate validity: `openssl x509 -in server.crt -text -noout`
- Use `verify_ssl=False` for testing (not for production)

### Debug Mode

Enable debug logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

Run server in debug mode:

```bash
python3 redfishMockupServer_enhanced.py -D mockup --debug
```

### Performance Profiling

```python
import cProfile
import pstats

# Profile code
profiler = cProfile.Profile()
profiler.enable()

# Run server code

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

---

## Contributing

We welcome contributions! Please see:

- [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community standards
- GitHub Issues for bugs and features

### Original Source Attribution

This project is based on the DMTF Redfish-Mockup-Server:
- Original Project: https://github.com/DMTF/Redfish-Mockup-Server
- Copyright 2016-2020 DMTF. All rights reserved.
- Licensed under the same terms as the original project

---

## Resources

### Documentation
- [Redfish Specification](https://www.dmtf.org/standards/redfish)
- [Redfish Developer Hub](https://www.dmtf.org/redfish)
- [DMTF Documentation](https://www.dmtf.org/documentation)

### Tools
- [Redfish Service Validator](https://github.com/DMTF/Redfish-Service-Validator)
- [Redfish Mockup Creator](https://github.com/DMTF/Redfish-Mockup-Creator)
- [Redfish Interop Validator](https://github.com/DMTF/Redfish-Interop-Validator)

### Community
- [DMTF Redfish Forum](https://www.dmtf.org/standards/feedback)
- [Stack Overflow - Redfish](https://stackoverflow.com/questions/tagged/redfish)

### Upstream Project
- [DMTF Redfish-Mockup-Server](https://github.com/DMTF/Redfish-Mockup-Server)

---

## License

This project is based on DMTF Redfish-Mockup-Server.  
Copyright 2016-2025 DMTF. All rights reserved.

See [LICENSE.md](LICENSE.md) for full license text.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

---

**Last Updated**: November 5, 2025  
**Version**: 2.0.0