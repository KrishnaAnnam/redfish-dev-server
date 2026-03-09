# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
# Defining New Redfish Requirements with BMC Simulator
## Complete Presentation & Demo Guide

---

## 🎯 Presentation: "From Concept to Implementation - Defining Redfish Requirements"

### **Slide 1: Title Slide**
```
Defining New Redfish Requirements
Using BMC Redfish Simulator

From Concept to Implementation:
A Developer's Guide to Redfish Requirement Definition

[Logo/Graphic: Redfish + Development Workflow]
```

### **Slide 2: The Challenge - Redfish Development Pain Points**
```
Current Redfish Development Challenges:

🔴 Requirements Definition Issues:
• Unclear API specifications lead to implementation gaps
• Missing edge case handling and error scenarios
• Inconsistent behavior across different BMC vendors
• Lack of validation tools for new requirements

🔴 Development & Testing Problems:
• Expensive hardware dependency for requirement validation
• Time-consuming iteration cycles
• Difficulty reproducing specific scenarios
• Limited automation for requirement verification

💡 Solution: Use BMC Simulator to define, validate, and test requirements iteratively
```

### **Slide 3: Requirement Definition Methodology**
```
Systematic Approach to Redfish Requirement Definition:

1. 📝 ANALYZE: Understand business needs and use cases
2. 🎯 DESIGN: Define API structure and behavior specifications  
3. 🧪 PROTOTYPE: Implement mock behavior in simulator
4. ✅ VALIDATE: Test against real scenarios and edge cases
5. 🔄 ITERATE: Refine based on testing feedback
6. 📋 DOCUMENT: Create comprehensive requirement specifications
7. 🚀 IMPLEMENT: Develop production BMC firmware

Benefits: Faster cycles, better quality, reduced risk
```

### **Slide 4: Simulator-Based Requirement Development**
```
How BMC Simulator Accelerates Requirement Definition:

🎨 Rapid Prototyping:
• Quick API endpoint creation and modification
• Immediate behavior testing and validation
• Multiple scenario simulation

🧪 Comprehensive Testing:
• Edge case exploration and handling
• Error condition simulation
• Performance characteristic modeling

🔄 Iterative Refinement:
• Fast feedback loops with stakeholders
• Easy specification adjustments
• Continuous validation during development

📊 Specification Validation:
• Automated compliance checking
• Consistent behavior verification
• Documentation accuracy validation
```

### **Slide 5: Demo Overview**
```
Live Demo: Creating a Custom Power Management Requirement

Scenario: Define enhanced power capping functionality
• Custom OEM power policy management
• Advanced thermal protection algorithms
• Multi-zone power allocation control

Demo Flow:
1. Requirement Analysis & Design
2. Mock API Implementation  
3. Behavior Simulation & Testing
4. Error Handling & Edge Cases
5. Documentation Generation
6. Client Integration Validation
```

---

## 🎥 Live Demo Script

### **Part 1: Requirement Analysis (5 minutes)**

**Demo Setup:**
```bash
# Start with clean environment
cd .
python servers/redfishMockupServer_platform.py -D mockups/public-rackmount1 &
SERVER_PID=$!
```

**Requirement Definition:**
```
Business Need: Enhanced Power Management for Data Centers

Current Limitations:
• Basic power capping insufficient for modern workloads
• Need zone-based power allocation
• Require predictive power management
• Must support custom power policies

New Requirements:
1. PowerZones collection for multi-zone management
2. CustomPowerPolicy resource for advanced algorithms  
3. PowerPrediction service for forecasting
4. Enhanced power monitoring with sub-second sampling
```

### **Part 2: Mock API Implementation (10 minutes)**

**Create Custom Power Zones Resource:**

<function_calls>
<invoke name="create_file">
<parameter name="content">#!/usr/bin/env python3
"""
Demo: Custom Power Management Requirement Definition
===================================================

This demo shows how to define and implement new Redfish requirements
using the BMC Simulator for enhanced power management capabilities.
"""

import json
import os
import shutil
import requests
import time
from pathlib import Path

class PowerManagementRequirementDemo:
    def __init__(self):
        self.base_url = "http://localhost:8000/redfish/v1"
        self.mockup_path = "mockups/public-rackmount1"
        self.demo_path = "demo_requirements"
        
    def setup_demo_environment(self):
        """Setup demo environment with custom mockup data"""
        print("🎬 Setting up Power Management Requirement Demo")
        print("=" * 50)
        
        # Create demo directory structure
        demo_mockup = f"{self.demo_path}/power_management_mockup"
        if os.path.exists(self.demo_path):
            shutil.rmtree(self.demo_path)
        
        # Copy base mockup
        shutil.copytree(self.mockup_path, demo_mockup)
        
        print(f"✅ Created demo mockup at: {demo_mockup}")
        return demo_mockup
    
    def define_power_zones_requirement(self, demo_mockup):
        """Step 1: Define PowerZones collection requirement"""
        print("\n📝 Step 1: Defining PowerZones Collection Requirement")
        print("-" * 50)
        
        # Create PowerZones collection schema
        power_zones_schema = {
            "@odata.type": "#PowerZoneCollection.PowerZoneCollection",
            "@odata.id": "/redfish/v1/Chassis/1U/PowerZones",
            "Name": "Power Zones Collection", 
            "Description": "Collection of power management zones",
            "Members@odata.count": 3,
            "Members": [
                {"@odata.id": "/redfish/v1/Chassis/1U/PowerZones/CPU"},
                {"@odata.id": "/redfish/v1/Chassis/1U/PowerZones/Memory"},
                {"@odata.id": "/redfish/v1/Chassis/1U/PowerZones/Storage"}
            ]
        }
        
        # Create directory structure
        zones_dir = f"{demo_mockup}/Chassis/1U/PowerZones"
        os.makedirs(zones_dir, exist_ok=True)
        
        # Write collection
        with open(f"{zones_dir}/index.json", "w") as f:
            json.dump(power_zones_schema, f, indent=2)
        
        print("✅ Created PowerZones collection schema")
        self.print_json_snippet(power_zones_schema)
        
        return zones_dir
    
    def define_power_zone_resource(self, zones_dir):
        """Step 2: Define individual PowerZone resource"""
        print("\n🔧 Step 2: Defining PowerZone Resource Schema")
        print("-" * 50)
        
        # CPU Power Zone definition
        cpu_power_zone = {
            "@odata.type": "#PowerZone.v1_0_0.PowerZone",
            "@odata.id": "/redfish/v1/Chassis/1U/PowerZones/CPU",
            "Id": "CPU",
            "Name": "CPU Power Zone",
            "Description": "Power management for CPU subsystem",
            "Status": {
                "State": "Enabled",
                "Health": "OK"
            },
            "PowerCapacityWatts": 300,
            "PowerAllocatedWatts": 180,
            "PowerAvailableWatts": 120,
            "PowerDemandPercent": 60.5,
            "PowerPolicy": {
                "PolicyType": "Adaptive",
                "MaxPowerWatts": 300,
                "MinPowerWatts": 50,
                "PowerLimitPolicy": "HardPowerOff"
            },
            "PowerMetrics": {
                "IntervalInMin": 1,
                "MinConsumedWatts": 45,
                "MaxConsumedWatts": 275,
                "AverageConsumedWatts": 180
            },
            "Actions": {
                "#PowerZone.SetPowerLimit": {
                    "target": "/redfish/v1/Chassis/1U/PowerZones/CPU/Actions/PowerZone.SetPowerLimit",
                    "PowerLimitWatts@Redfish.AllowableValues": [50, 100, 150, 200, 250, 300]
                },
                "Oem": {
                    "Vendor": {
                        "#VendorPowerZone.SetAdvancedPolicy": {
                            "target": "/redfish/v1/Chassis/1U/PowerZones/CPU/Actions/Oem/Vendor.SetAdvancedPolicy",
                            "PolicyName@Redfish.AllowableValues": ["PerformanceFirst", "EfficiencyFirst", "Balanced", "Custom"]
                        }
                    }
                }
            },
            "Oem": {
                "Vendor": {
                    "PowerPrediction": {
                        "PredictionWindowMinutes": 30,
                        "PredictedPeakWatts": 245,
                        "PredictedAverageWatts": 195,
                        "ConfidenceLevel": 85.2
                    },
                    "ThermalIntegration": {
                        "MaxThermalWatts": 280,
                        "CurrentThermalLimit": 275,
                        "ThermalThrottleActive": False
                    }
                }
            }
        }
        
        # Create CPU zone
        cpu_dir = f"{zones_dir}/CPU"
        os.makedirs(cpu_dir, exist_ok=True)
        
        with open(f"{cpu_dir}/index.json", "w") as f:
            json.dump(cpu_power_zone, f, indent=2)
            
        print("✅ Created CPU PowerZone resource")
        self.print_json_snippet(cpu_power_zone, max_lines=15)
        
        return cpu_dir
    
    def define_custom_actions(self, cpu_dir):
        """Step 3: Define custom action behaviors"""
        print("\n⚡ Step 3: Defining Custom Action Behaviors")
        print("-" * 50)
        
        # SetPowerLimit action response
        set_power_limit_action = {
            "@odata.type": "#PowerZone.v1_0_0.SetPowerLimit",
            "Description": "Set power limit for the power zone",
            "Parameters": {
                "PowerLimitWatts": {
                    "Required": True,
                    "DataType": "Number",
                    "AllowableValues": [50, 100, 150, 200, 250, 300]
                },
                "PowerLimitPolicy": {
                    "Required": False,
                    "DataType": "String", 
                    "AllowableValues": ["NoAction", "HardPowerOff", "Throttle"]
                }
            }
        }
        
        # Custom Vendor OEM action
        vendor_advanced_policy = {
            "@odata.type": "#VendorPowerZone.v1_0_0.SetAdvancedPolicy",
            "Description": "Configure advanced power management policy",
            "Parameters": {
                "PolicyName": {
                    "Required": True,
                    "DataType": "String",
                    "AllowableValues": ["PerformanceFirst", "EfficiencyFirst", "Balanced", "Custom"]
                },
                "CustomParameters": {
                    "Required": False,
                    "DataType": "Object",
                    "Description": "Custom policy parameters when PolicyName is 'Custom'"
                }
            }
        }
        
        # Create Actions directory
        actions_dir = f"{cpu_dir}/Actions"
        os.makedirs(actions_dir, exist_ok=True)
        
        # Create action definitions
        os.makedirs(f"{actions_dir}/PowerZone.SetPowerLimit", exist_ok=True)
        with open(f"{actions_dir}/PowerZone.SetPowerLimit/index.json", "w") as f:
            json.dump(set_power_limit_action, f, indent=2)
        
        os.makedirs(f"{actions_dir}/Oem/Vendor.SetAdvancedPolicy", exist_ok=True)
        with open(f"{actions_dir}/Oem/Vendor.SetAdvancedPolicy/index.json", "w") as f:
            json.dump(vendor_advanced_policy, f, indent=2)
            
        print("✅ Created custom action definitions")
        print(f"   • SetPowerLimit: Standard power limiting")
        print(f"   • SetAdvancedPolicy: OEM-specific advanced policies")
        
    def create_requirement_documentation(self):
        """Step 4: Generate requirement documentation"""
        print("\n📋 Step 4: Generating Requirement Documentation")
        print("-" * 50)
        
        requirement_doc = f"""# Enhanced Power Management Requirements

## Overview
This document defines new Redfish requirements for enhanced power management capabilities in BMC systems.

## Business Justification
- **Data Center Efficiency**: Need for zone-based power management
- **Predictive Analytics**: Require power consumption forecasting
- **Advanced Policies**: Support for custom power management algorithms
- **Thermal Integration**: Coordinate power and thermal management

## New Resource Definitions

### 1. PowerZones Collection
- **URI Pattern**: `/redfish/v1/Chassis/{{ChassisId}}/PowerZones`
- **Purpose**: Manage multiple power zones within a chassis
- **Members**: Individual PowerZone resources

### 2. PowerZone Resource  
- **URI Pattern**: `/redfish/v1/Chassis/{{ChassisId}}/PowerZones/{{ZoneId}}`
- **Purpose**: Manage power for specific system components
- **Key Properties**:
  - PowerCapacityWatts: Maximum zone power capacity
  - PowerAllocatedWatts: Currently allocated power
  - PowerAvailableWatts: Available for allocation
  - PowerDemandPercent: Current demand percentage
  - PowerPolicy: Zone-specific power policies
  - PowerMetrics: Historical power consumption data

### 3. Custom Actions

#### SetPowerLimit
- **Purpose**: Configure power limits for zone
- **Parameters**: 
  - PowerLimitWatts (required): Limit value
  - PowerLimitPolicy (optional): Action when exceeded

#### OEM Vendor.SetAdvancedPolicy  
- **Purpose**: Configure advanced power management
- **Parameters**:
  - PolicyName (required): Policy selection
  - CustomParameters (optional): Custom policy configuration

### 4. OEM Extensions

#### PowerPrediction
- **Purpose**: Predictive power management
- **Properties**:
  - PredictionWindowMinutes: Forecast window
  - PredictedPeakWatts: Expected peak consumption
  - PredictedAverageWatts: Expected average consumption
  - ConfidenceLevel: Prediction confidence percentage

#### ThermalIntegration
- **Purpose**: Coordinate power and thermal management
- **Properties**:
  - MaxThermalWatts: Thermal-limited power capacity
  - CurrentThermalLimit: Current thermal constraint
  - ThermalThrottleActive: Indicates active thermal throttling

## Implementation Requirements

### BMC Firmware Requirements
1. **Zone Management**: Implement power zone discovery and management
2. **Policy Engine**: Support configurable power policies
3. **Prediction Engine**: Implement power consumption forecasting
4. **Thermal Coordination**: Integrate with thermal management systems

### Client Requirements
1. **Discovery**: Support PowerZones collection enumeration
2. **Configuration**: Implement power policy configuration
3. **Monitoring**: Support real-time power monitoring
4. **Actions**: Handle SetPowerLimit and OEM actions

## Validation Criteria

### Functional Validation
- [ ] PowerZones collection properly enumerated
- [ ] Individual PowerZone resources accessible
- [ ] SetPowerLimit action functions correctly
- [ ] OEM actions execute properly
- [ ] Power metrics updated in real-time

### Performance Validation  
- [ ] Zone discovery < 100ms
- [ ] Action execution < 500ms
- [ ] Metrics update frequency >= 1Hz
- [ ] Prediction accuracy >= 80%

### Error Handling Validation
- [ ] Invalid power limits rejected
- [ ] Unsupported policies return appropriate errors  
- [ ] Resource access permissions enforced
- [ ] Graceful degradation when features unavailable

## Test Scenarios

### Basic Functionality
1. Enumerate PowerZones collection
2. Access individual PowerZone resources
3. Execute SetPowerLimit action
4. Configure advanced policies
5. Monitor power metrics

### Edge Cases
1. Invalid power limit values
2. Unsupported policy configurations  
3. Resource access without permissions
4. Zone unavailable conditions
5. Thermal override scenarios

### Performance Testing
1. High-frequency metric sampling
2. Concurrent zone management
3. Prediction accuracy validation
4. Policy change responsiveness

## Compliance Considerations

### Redfish Compliance
- Follow Redfish URI conventions
- Use standard HTTP status codes
- Implement proper ETag support
- Support standard Redfish headers

### Security Considerations
- Enforce role-based access control
- Validate action parameters
- Audit power management changes
- Secure OEM extension access

---
Generated by BMC Redfish Simulator Requirement Demo
Date: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""

        # Write documentation
        doc_path = f"{self.demo_path}/POWER_MANAGEMENT_REQUIREMENTS.md"
        with open(doc_path, "w") as f:
            f.write(requirement_doc)
        
        print(f"✅ Generated comprehensive requirement documentation")
        print(f"   📄 Location: {doc_path}")
        return doc_path
    
    def test_requirement_scenarios(self, demo_mockup):
        """Step 5: Test requirement scenarios"""
        print("\n🧪 Step 5: Testing Requirement Scenarios")
        print("-" * 50)
        
        # Start server with demo mockup
        import subprocess
        print(f"🚀 Starting server with demo mockup...")
        
        server_cmd = f"python servers/redfishMockupServer_platform.py -D {demo_mockup} -p 8001"
        print(f"   Command: {server_cmd}")
        
        # Test scenarios
        test_scenarios = [
            "1. Enumerate PowerZones collection",
            "2. Access CPU PowerZone resource", 
            "3. Test SetPowerLimit action",
            "4. Validate error handling",
            "5. Check OEM extensions"
        ]
        
        print("\n🔍 Test Scenarios to Execute:")
        for scenario in test_scenarios:
            print(f"   {scenario}")
            
        print("\n💡 Manual Testing Commands:")
        print(f"   # Start demo server:")
        print(f"   {server_cmd}")
        print(f"   ")
        print(f"   # Test PowerZones collection:")
        print(f"   curl http://localhost:8001/redfish/v1/Chassis/1U/PowerZones")
        print(f"   ")
        print(f"   # Test CPU PowerZone:")  
        print(f"   curl http://localhost:8001/redfish/v1/Chassis/1U/PowerZones/CPU")
        print(f"   ")
        print(f"   # Test SetPowerLimit action:")
        print(f"   curl -X POST -H 'Content-Type: application/json' \\")
        print(f"        -d '{{"PowerLimitWatts": 250}}' \\")
        print(f"        http://localhost:8001/redfish/v1/Chassis/1U/PowerZones/CPU/Actions/PowerZone.SetPowerLimit")
    
    def generate_client_examples(self):
        """Step 6: Generate client integration examples"""
        print("\n👨‍💻 Step 6: Generating Client Integration Examples")
        print("-" * 50)
        
        client_example = '''#!/usr/bin/env python3
"""
Power Management Client Example
==============================

Demonstrates how to use the enhanced power management requirements
with the BMC Redfish Simulator.
"""

import requests
import json

class PowerManagementClient:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def discover_power_zones(self, chassis_id="1U"):
        """Discover available power zones"""
        url = f"{self.base_url}/redfish/v1/Chassis/{chassis_id}/PowerZones"
        response = self.session.get(url)
        
        if response.status_code == 200:
            zones = response.json()
            print(f"Found {zones['Members@odata.count']} power zones:")
            for member in zones['Members']:
                print(f"  • {member['@odata.id']}")
            return zones
        else:
            print(f"Error discovering zones: {response.status_code}")
            return None
    
    def get_zone_details(self, zone_uri):
        """Get detailed information about a power zone"""
        url = f"{self.base_url}{zone_uri}"
        response = self.session.get(url)
        
        if response.status_code == 200:
            zone = response.json()
            print(f"\\nZone: {zone['Name']}")
            print(f"Capacity: {zone['PowerCapacityWatts']}W")
            print(f"Allocated: {zone['PowerAllocatedWatts']}W") 
            print(f"Available: {zone['PowerAvailableWatts']}W")
            print(f"Demand: {zone['PowerDemandPercent']}%")
            
            # Show OEM extensions
            if 'Oem' in zone and 'Vendor' in zone['Oem']:
                oem_ext = zone['Oem']['Vendor']
                if 'PowerPrediction' in oem_ext:
                    pred = oem_ext['PowerPrediction']
                    print(f"Predicted Peak: {pred['PredictedPeakWatts']}W")
                    print(f"Confidence: {pred['ConfidenceLevel']}%")
            
            return zone
        else:
            print(f"Error getting zone details: {response.status_code}")
            return None
    
    def set_power_limit(self, zone_uri, power_limit_watts, policy="HardPowerOff"):
        """Set power limit for a zone"""
        action_uri = f"{zone_uri}/Actions/PowerZone.SetPowerLimit"
        url = f"{self.base_url}{action_uri}"
        
        payload = {
            "PowerLimitWatts": power_limit_watts,
            "PowerLimitPolicy": policy
        }
        
        response = self.session.post(url, json=payload)
        
        if response.status_code in [200, 202, 204]:
            print(f"✅ Power limit set to {power_limit_watts}W")
            return True
        else:
            print(f"❌ Failed to set power limit: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    
    def set_advanced_policy(self, zone_uri, policy_name, custom_params=None):
        """Set advanced power policy (OEM extension)"""
        action_uri = f"{zone_uri}/Actions/Oem/Vendor.SetAdvancedPolicy"
        url = f"{self.base_url}{action_uri}"
        
        payload = {"PolicyName": policy_name}
        if custom_params:
            payload["CustomParameters"] = custom_params
        
        response = self.session.post(url, json=payload)
        
        if response.status_code in [200, 202, 204]:
            print(f"✅ Advanced policy set to {policy_name}")
            return True
        else:
            print(f"❌ Failed to set policy: {response.status_code}")
            return False

def main():
    """Demonstrate power management client usage"""
    print("🔋 Power Management Client Demo")
    print("=" * 40)
    
    # Create client
    client = PowerManagementClient()
    
    # Discover power zones
    zones = client.discover_power_zones()
    if not zones:
        return
    
    # Get details for CPU zone
    cpu_zone_uri = "/redfish/v1/Chassis/1U/PowerZones/CPU"
    zone_details = client.get_zone_details(cpu_zone_uri)
    if not zone_details:
        return
    
    # Set power limit
    print("\\n🔧 Setting power limit to 250W...")
    client.set_power_limit(cpu_zone_uri, 250)
    
    # Set advanced policy
    print("\\n⚙️ Setting efficiency-first policy...")
    client.set_advanced_policy(cpu_zone_uri, "EfficiencyFirst")
    
    # Set custom policy
    print("\\n🎛️ Setting custom policy...")
    custom_params = {
        "MaxFrequencyMHz": 3200,
        "PowerEfficiencyTarget": 85,
        "ThermalThreshold": 75
    }
    client.set_advanced_policy(cpu_zone_uri, "Custom", custom_params)

if __name__ == "__main__":
    main()
'''
        
        # Write client example
        client_path = f"{self.demo_path}/power_management_client.py"
        with open(client_path, "w") as f:
            f.write(client_example)
        
        print(f"✅ Generated client integration example")
        print(f"   🐍 Location: {client_path}")
        return client_path
    
    def print_json_snippet(self, data, max_lines=10):
        """Helper to print JSON snippet"""
        json_str = json.dumps(data, indent=2)
        lines = json_str.split('\n')
        
        print("   📄 Schema snippet:")
        for i, line in enumerate(lines[:max_lines]):
            print(f"      {line}")
        if len(lines) > max_lines:
            print(f"      ... ({len(lines) - max_lines} more lines)")
    
    def run_complete_demo(self):
        """Run the complete requirement definition demo"""
        print("🎬 BMC Redfish Simulator - Requirement Definition Demo")
        print("=" * 60)
        print("Demonstrating: Enhanced Power Management Requirements")
        print()
        
        try:
            # Setup
            demo_mockup = self.setup_demo_environment()
            
            # Define requirements
            zones_dir = self.define_power_zones_requirement(demo_mockup)
            cpu_dir = self.define_power_zone_resource(zones_dir)
            self.define_custom_actions(cpu_dir)
            
            # Generate documentation
            doc_path = self.create_requirement_documentation()
            
            # Test scenarios
            self.test_requirement_scenarios(demo_mockup)
            
            # Client examples
            client_path = self.generate_client_examples()
            
            # Summary
            print("\n🎉 Demo Complete!")
            print("=" * 30)
            print("Generated Files:")
            print(f"  📁 Demo mockup: {demo_mockup}")
            print(f"  📄 Requirements: {doc_path}")
            print(f"  🐍 Client example: {client_path}")
            print()
            print("Next Steps:")
            print("1. Review generated requirements documentation")
            print("2. Test with demo server and client")
            print("3. Refine requirements based on testing")
            print("4. Implement in production BMC firmware")
            
        except Exception as e:
            print(f"❌ Demo failed: {e}")
            raise

if __name__ == "__main__":
    demo = PowerManagementRequirementDemo()
    demo.run_complete_demo()