#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Action Handlers Demo for BMC Redfish Simulator
==============================================
Demonstrates how to:
1. Define actions in mockup resources
2. Implement custom action handlers
3. Call actions via POST requests
4. Handle action parameters and validation
5. Update resource state from action results
6. Receive EventService notifications

This example shows the complete flow of Redfish action implementation.
"""

import requests
import json
import time
from datetime import datetime


class ActionHandlersDemo:
    """Demo class for Action Handler operations"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def create_test_actions_in_mockup(self):
        """
        This shows how to define actions in your mockup resources.
        In a real scenario, you would edit the JSON files directly.
        """
        print("📝 Action definitions should be added to your mockup resources like this:")
        
        example_actions = {
            "ComputerSystem Actions": {
                "file": "public-rackmount1/Systems/437XR1138R2/index.json",
                "actions": {
                    "Actions": {
                        "#ComputerSystem.Reset": {
                            "target": "/redfish/v1/Systems/437XR1138R2/Actions/ComputerSystem.Reset",
                            "ResetType@Redfish.AllowableValues": [
                                "On", "ForceOff", "GracefulShutdown", "GracefulRestart", "ForceRestart", "PowerCycle"
                            ]
                        },
                        "#ComputerSystem.SetDefaultBootOrder": {
                            "target": "/redfish/v1/Systems/437XR1138R2/Actions/ComputerSystem.SetDefaultBootOrder"
                        }
                    }
                }
            },
            "TestService Actions": {
                "file": "public-rackmount1/TestService/index.json",
                "actions": {
                    "Actions": {
                        "#TestService.Reset": {
                            "target": "/redfish/v1/TestService/Actions/TestService.Reset",
                            "ResetType@Redfish.AllowableValues": ["On", "ForceOff", "GracefulRestart", "PowerCycle"]
                        },
                        "#TestService.RunDiagnostic": {
                            "target": "/redfish/v1/TestService/Actions/TestService.RunDiagnostic",
                            "DiagnosticType@Redfish.AllowableValues": ["Quick", "Extended", "Full"],
                            "TimeoutRange": "1-3600 seconds"
                        },
                        "#TestService.UpdateFirmware": {
                            "target": "/redfish/v1/TestService/Actions/TestService.UpdateFirmware"
                        }
                    }
                }
            },
            "Battery Actions": {
                "file": "public-rackmount1/Chassis/1U/PowerSubsystem/Batteries/Module1/index.json", 
                "actions": {
                    "Actions": {
                        "#Battery.SelfTest": {
                            "target": "/redfish/v1/Chassis/1U/PowerSubsystem/Batteries/Module1/Actions/Battery.SelfTest"
                        },
                        "#Battery.Calibrate": {
                            "target": "/redfish/v1/Chassis/1U/PowerSubsystem/Batteries/Module1/Actions/Battery.Calibrate"
                        }
                    }
                }
            }
        }
        
        for action_type, info in example_actions.items():
            print(f"\n{action_type}:")
            print(f"  File: {info['file']}")
            print(f"  Add to JSON: {json.dumps(info['actions'], indent=4)}")
        
        print("\n✅ Actions are already defined in the TestService mockup for demo purposes!")
    
    def test_action(self, action_url, action_data, description):
        """Test a specific action"""
        print(f"\n🔄 Testing: {description}")
        print(f"URL: {action_url}")
        print(f"Data: {json.dumps(action_data, indent=2)}")
        
        response = self.session.post(f"{self.base_url}{action_url}", json=action_data)
        print(f"Response: {response.status_code}")
        
        if response.status_code in [200, 201, 202, 204]:
            print("✅ Action completed successfully")
            if response.text and response.text.strip():
                try:
                    result = response.json()
                    print(f"Result: {json.dumps(result, indent=2)}")
                    return result
                except:
                    print(f"Response text: {response.text}")
            else:
                print("No response body (204 No Content)")
        else:
            print(f"❌ Action failed: {response.text}")
            
        return None
    
    def get_resource(self, resource_path):
        """Get resource to verify action effects"""
        response = self.session.get(f"{self.base_url}{resource_path}")
        if response.status_code == 200:
            return response.json()
        return None
    
    def run_demo(self):
        """Run the complete Action Handlers demo"""
        print("🚀 BMC Redfish Simulator - Action Handlers Demo")
        print("=" * 55)
        
        # 1. Show how to define actions
        print("\n1. Understanding Action Definitions...")
        self.create_test_actions_in_mockup()
        
        # 2. Test TestService.Reset action
        print("\n2. Testing TestService.Reset Action...")
        reset_result = self.test_action(
            "/redfish/v1/TestService/Actions/TestService.Reset",
            {"ResetType": "GracefulRestart"},
            "TestService Reset with GracefulRestart"
        )
        
        # 3. Test TestService.RunDiagnostic action 
        print("\n3. Testing TestService.RunDiagnostic Action...")
        diag_result = self.test_action(
            "/redfish/v1/TestService/Actions/TestService.RunDiagnostic", 
            {
                "DiagnosticType": "Full",
                "Timeout": 120
            },
            "Full diagnostic with 120 second timeout"
        )
        
        # 4. Test Battery.SelfTest action
        print("\n4. Testing Battery.SelfTest Action...")
        battery_result = self.test_action(
            "/redfish/v1/Chassis/1U/PowerSubsystem/Batteries/Module1/Actions/Battery.SelfTest",
            {},
            "Battery self-test"
        )
        
        # 5. Test Custom OEM action
        print("\n5. Testing Custom OEM Diagnostic Action...")
        oem_result = self.test_action(
            "/redfish/v1/TestService/Actions/Oem.CustomDiagnostic",
            {
                "TargetComponent": "PowerSupply",
                "TestLevel": "Comprehensive"
            },
            "Custom OEM diagnostic"
        )
        
        # 6. Test invalid action (should fail)
        print("\n6. Testing Invalid Action (should fail)...")
        self.test_action(
            "/redfish/v1/TestService/Actions/NonExistentAction",
            {},
            "Non-existent action (expected to fail)"
        )
        
        # 7. Test action with invalid parameters
        print("\n7. Testing Action with Invalid Parameters...")
        self.test_action(
            "/redfish/v1/TestService/Actions/TestService.RunDiagnostic",
            {
                "DiagnosticType": "InvalidType",  # Invalid value
                "Timeout": 5000  # Out of range
            },
            "Diagnostic with invalid parameters (expected to fail)"
        )
        
        # 8. Verify resource state changes
        print("\n8. Verifying Resource State Changes...")
        test_service = self.get_resource("/redfish/v1/TestService")
        if test_service:
            print(f"TestService Status: {test_service.get('Status', {})}")
            print(f"Last Reset: {test_service.get('LastResetTime', 'Not available')}")
            if 'DiagnosticResults' in test_service:
                print(f"Diagnostic Results Count: {len(test_service['DiagnosticResults'])}")
        
        battery = self.get_resource("/redfish/v1/Chassis/1U/PowerSubsystem/Batteries/Module1")
        if battery:
            print(f"Battery Status: {battery.get('Status', {})}")
            print(f"Last Test: {battery.get('LastTestTime', 'Not available')}")
            if 'TestResults' in battery:
                print(f"Test Results Count: {len(battery['TestResults'])}")
        
        print("\n✅ Action Handlers Demo completed!")
        print("\n📊 Summary:")
        print("- Actions are defined in mockup resource JSON files")
        print("- CustomActionsService routes and handles actions")
        print("- Action handlers validate parameters and update resources")
        print("- Resource state changes persist to the mockup tree")
        print("- EventService notifications are triggered automatically")
        print("- All operations integrate with the existing simulator architecture")


def create_example_action_definition():
    """Show how to add a new action to a resource"""
    print("\n" + "="*60)
    print("HOW TO ADD A NEW ACTION TO A RESOURCE")
    print("="*60)
    
    steps = [
        {
            "step": "1. Define Action in Resource JSON",
            "description": "Add action definition to the resource's index.json file",
            "example": """
// In public-rackmount1/Systems/437XR1138R2/index.json
{
    "@odata.type": "#ComputerSystem.v1_17_0.ComputerSystem",
    "Id": "437XR1138R2", 
    "Name": "Computer System",
    // ... other properties ...
    "Actions": {
        "#ComputerSystem.Reset": {
            "target": "/redfish/v1/Systems/437XR1138R2/Actions/ComputerSystem.Reset",
            "ResetType@Redfish.AllowableValues": [
                "On", "ForceOff", "GracefulShutdown", "GracefulRestart", "ForceRestart", "PowerCycle"
            ]
        },
        "#ComputerSystem.MyCustomAction": {
            "target": "/redfish/v1/Systems/437XR1138R2/Actions/ComputerSystem.MyCustomAction",
            "Parameter1@Redfish.AllowableValues": ["Value1", "Value2", "Value3"],
            "Parameter2": "Description of parameter 2"
        }
    }
}
""".strip()
        },
        {
            "step": "2. Add Handler to CustomActionsService",
            "description": "Implement the action logic in custom_actions_service.py",
            "example": """
# In src/services/custom_actions_service.py

def __init__(self, server_config):
    # ... existing init code ...
    self.action_handlers = {
        # ... existing handlers ...
        'ComputerSystem.MyCustomAction': self._handle_my_custom_action,
    }

def _handle_my_custom_action(self, action_path, resource_path, data_received, 
                           resource_data, cached_links):
    \"\"\"Handle ComputerSystem.MyCustomAction\"\"\"
    
    # 1. Validate parameters
    param1 = data_received.get('Parameter1')
    param2 = data_received.get('Parameter2', 'default_value')
    
    if param1 not in ['Value1', 'Value2', 'Value3']:
        return 400, {}, {"error": "Invalid Parameter1"}
    
    # 2. Perform action logic
    result = {
        "ActionId": f"action_{int(time.time())}",
        "Status": "Completed",
        "Parameter1": param1,
        "Parameter2": param2,
        "Timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    
    # 3. Update resource state if needed
    resource_data['LastCustomAction'] = result
    self._update_resource_data(resource_path, resource_data, cached_links)
    
    # 4. Trigger event
    self._trigger_action_event('ComputerSystem.MyCustomAction', resource_path, 
                              data_received, 'Success')
    
    # 5. Return response
    return 200, {}, result
""".strip()
        },
        {
            "step": "3. Test Your Action",
            "description": "Use curl or similar tool to test the new action",
            "example": """
# Test the new action
curl -X POST http://localhost:8000/redfish/v1/Systems/437XR1138R2/Actions/ComputerSystem.MyCustomAction \\
  -H "Content-Type: application/json" \\
  -d '{
    "Parameter1": "Value2",
    "Parameter2": "my_custom_value"
  }'

# Expected response:
{
  "ActionId": "action_1699123456",
  "Status": "Completed", 
  "Parameter1": "Value2",
  "Parameter2": "my_custom_value",
  "Timestamp": "2024-11-11T12:30:00Z"
}
""".strip()
        }
    ]
    
    for step_info in steps:
        print(f"\n{step_info['step']}:")
        print(f"{step_info['description']}")
        print(f"\nExample:")
        print(step_info['example'])
    
    print("\n" + "="*60)


def main():
    """Main demo function"""
    # Note: Make sure the BMC Redfish Simulator is running first:
    # python3 redfishMockupServer_modular.py -D public-rackmount1 -S -p 8000
    
    demo = ActionHandlersDemo()
    demo.run_demo()
    
    create_example_action_definition()


if __name__ == "__main__":
    main()