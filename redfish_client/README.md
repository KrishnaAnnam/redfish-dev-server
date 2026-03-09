# Redfish Client Library

**Project:** bmc-redfish-simulator  
**Module:** redfish_client

A comprehensive Python library for interacting with BMC (Baseboard Management Controller) systems using the Redfish API standard.

## Overview

This client library is part of the BMC Redfish Simulator project and provides a complete toolkit for developers to build Redfish clients for BMC simulation and interaction. It includes core client functionality, monitoring capabilities, testing tools, and utility applications.

## Package Structure

```
redfish_client/
├── client.py              # Core Redfish client library
├── monitoring.py          # Advanced monitoring and alerting
├── __init__.py           # Package initialization
├── examples/             # Usage examples
│   ├── basic_examples.py # Comprehensive client examples
│   └── __init__.py
├── tests/               # Test suite
│   ├── basic_test.py    # Basic functionality tests
│   ├── test_suite.py    # Complete test suite
│   └── __init__.py
└── tools/               # Utility applications
    ├── web_dashboard.py # Web-based monitoring dashboard
    ├── launcher.py      # Interactive demo launcher
    └── __init__.py
```

## Quick Start

### 1. Import the Library

```python
from redfish_client.client import RedfishClient
from redfish_client.monitoring import RedfishMonitoringClient
```

### 2. Basic Usage

```python
# Create client instance
client = RedfishClient("http://localhost:8000", "admin", "password")

# Connect to BMC
if client.connect():
    # Get system information
    systems = client.get_systems()
    print(f"Available systems: {systems}")
    
    # Monitor system health
    health = client.get_system_health()
    print(f"System health: {health}")
```

### 3. Real-time Monitoring

```python
# Create monitoring client
monitor = RedfishMonitoringClient("http://localhost:8000", "admin", "password")

# Start monitoring (1-minute demo)
monitor.start_monitoring(duration=60, alert_threshold=80.0)
```

## Features

### Core Client (`client.py`)
- **Session Management**: Automatic authentication and session handling
- **System Information**: Retrieve system details, health, and status
- **Power Management**: Control system power states (on/off/reset)
- **Event Subscriptions**: Subscribe to and manage system events
- **Error Handling**: Comprehensive error management and logging

### Monitoring Client (`monitoring.py`)
- **Real-time Monitoring**: Continuous system health monitoring
- **Alert System**: Configurable threshold-based alerts
- **Metrics Collection**: CPU, memory, temperature, and power metrics
- **Health Scoring**: Automated health assessment and scoring
- **Report Generation**: Detailed monitoring reports

### Web Dashboard (`tools/web_dashboard.py`)
- **Browser Interface**: Web-based monitoring and control
- **Real-time Updates**: Live system status and metrics
- **Interactive Controls**: Power management through web UI
- **Visual Monitoring**: Charts and graphs for system metrics

## Examples

### Run All Examples
```bash
python redfish_client/examples/basic_examples.py
```

### Individual Examples
```python
# System discovery
from redfish_client.examples.basic_examples import system_discovery_example
system_discovery_example()

# Power management
from redfish_client.examples.basic_examples import power_management_example
power_management_example()

# Event monitoring
from redfish_client.examples.basic_examples import event_monitoring_example
event_monitoring_example()
```

## Testing

### Run Basic Tests
```bash
python redfish_client/tests/basic_test.py
```

### Run Complete Test Suite
```bash
python redfish_client/tests/test_suite.py
```

### Test Coverage
The test suite includes:
- Connection and authentication tests
- System information retrieval tests
- Power management tests
- Event subscription tests
- Error handling validation
- Performance benchmarks

## Tools and Utilities

### Interactive Demo Launcher
```bash
python redfish_client_launcher.py
```

### Web Dashboard
```bash
python redfish_client/tools/web_dashboard.py
```
Then open: http://localhost:5000

## Configuration

### Client Configuration
```python
client = RedfishClient(
    base_url="http://localhost:8000",
    username="admin", 
    password="password",
    timeout=30,
    verify_ssl=False,
    max_retries=3
)
```

### Monitoring Configuration
```python
monitor = RedfishMonitoringClient(
    base_url="http://localhost:8000",
    username="admin",
    password="password"
)

# Configure monitoring parameters
monitor.start_monitoring(
    duration=300,           # 5 minutes
    interval=5,            # Check every 5 seconds
    alert_threshold=85.0,  # Alert at 85% utilization
    enable_reports=True    # Generate reports
)
```

## Error Handling

The library provides comprehensive error handling:

```python
try:
    client = RedfishClient("http://localhost:8000", "admin", "password")
    if client.connect():
        systems = client.get_systems()
    else:
        print("Failed to connect to BMC")
except RedfishConnectionError as e:
    print(f"Connection error: {e}")
except RedfishAuthenticationError as e:
    print(f"Authentication failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Dependencies

- **requests**: HTTP client library
- **json**: JSON data handling (built-in)
- **time**: Time operations (built-in)
- **datetime**: Date/time handling (built-in)
- **flask**: Web dashboard (optional)

## Installation

1. Ensure Python 3.7+ is installed
2. Install dependencies:
```bash
pip install requests flask
```
3. Import the library in your Python code

## Integration with BMC Simulator

This library is designed to work with the enhanced Redfish BMC Simulator:

1. Start the BMC Simulator:
```bash
python ../servers/redfishMockupServer.py -D mockups/public-rackmount1 -p 8000
```

2. Use the client library to interact:
```python
client = RedfishClient("http://localhost:8000", "admin", "password")
```

## Support and Documentation

### Getting Help
- Run the interactive launcher for guided demos
- Check examples in `redfish_client/examples/`
- Review test cases in `redfish_client/tests/`
- Use the web dashboard for visual monitoring

### Best Practices
1. Always check connection status before operations
2. Use monitoring client for long-running observations
3. Handle exceptions appropriately
4. Close sessions when finished
5. Use appropriate timeouts for your environment

### Performance Tips
- Reuse client instances when possible
- Use batch operations for multiple requests
- Configure appropriate timeouts
- Monitor system resources during intensive operations

## License

This library is part of the Redfish BMC Simulator project and follows the same licensing terms.

## Version

Current version: 2.0.0 (2025-11-05)

## Project Attribution

This client library is part of the **bmc-redfish-simulator** project, which is based on the DMTF Redfish-Mockup-Server.

For more information:
- Main project: See [PROJECT_INFO.md](../PROJECT_INFO.md)
- Developer documentation: See [DEVELOPERS_GUIDE.md](../DEVELOPERS_GUIDE.md)
- Upstream project: [DMTF Redfish-Mockup-Server](https://github.com/DMTF/Redfish-Mockup-Server)