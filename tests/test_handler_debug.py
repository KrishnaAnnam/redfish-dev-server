#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Simple test to debug the property conflict
"""
import sys
import os
import json

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_individual_handlers():
    """Test if individual handler classes can be instantiated"""
    
    # Mock config
    class MockConfig:
        def __init__(self):
            self.mockdir = 'mockups/public-rackmount1'
            self.host = 'localhost'
            self.port = 8000
    
    # Mock server
    class MockServer:
        def __init__(self):
            self.config = MockConfig()
    
    # Mock request and client address
    class MockRequest:
        pass
    
    mock_server = MockServer()
    mock_request = MockRequest()
    mock_client_address = ('127.0.0.1', 12345)
    
    try:
        print("Testing PostHandler...")
        from handlers.post_handler import PostHandler
        
        # Create a simple test class that inherits only from PostHandler
        class TestPostHandler(PostHandler):
            def __init__(self, request, client_address, server):
                # Try to initialize just PostHandler
                super().__init__(request, client_address, server)
        
        post_handler = TestPostHandler(mock_request, mock_client_address, mock_server)
        print("✅ PostHandler works individually")
        
    except Exception as e:
        print(f"❌ PostHandler failed: {e}")
    
    try:
        print("Testing PatchHandler...")
        from handlers.patch_handler import PatchHandler
        
        # Create a simple test class that inherits only from PatchHandler  
        class TestPatchHandler(PatchHandler):
            def __init__(self, request, client_address, server):
                # Try to initialize just PatchHandler
                super().__init__(request, client_address, server)
        
        patch_handler = TestPatchHandler(mock_request, mock_client_address, mock_server)
        print("✅ PatchHandler works individually")
        
    except Exception as e:
        print(f"❌ PatchHandler failed: {e}")
    
    try:
        print("Testing Multiple Inheritance...")
        from handlers.post_handler import PostHandler
        from handlers.patch_handler import PatchHandler
        from handlers.base_handler import BaseRedfishHandler
        
        # Test the exact combination that's failing
        class TestCombinedHandler(PostHandler, PatchHandler):
            def __init__(self, request, client_address, server):
                super().__init__(request, client_address, server)
        
        combined_handler = TestCombinedHandler(mock_request, mock_client_address, mock_server)
        print("✅ Multiple inheritance works")
        
    except Exception as e:
        print(f"❌ Multiple inheritance failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_individual_handlers()