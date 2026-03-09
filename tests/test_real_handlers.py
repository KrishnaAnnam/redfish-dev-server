#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Test if there's a conflict between properties by trying to create the actual handler classes
"""

import sys
import os

# Add src directory to path  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_individual_handlers():
    """Test individual handler imports and instantiation"""
    
    # Mock objects
    class MockServer:
        def __init__(self):
            from types import SimpleNamespace
            self.config = SimpleNamespace()
            self.config.mock_dir = "public-rackmount1"
            self.config.short_form = False
    
    class MockRequest:
        pass
    
    try:
        print("Testing BaseRedfishHandler import...")
        from handlers.base_handler import BaseRedfishHandler
        print("✅ BaseRedfishHandler imported successfully")
        
        # Test base handler initialization
        print("Testing BaseRedfishHandler instantiation...")
        server = MockServer()
        request = MockRequest()
        base_handler = BaseRedfishHandler(request, ('127.0.0.1', 12345), server)
        print("✅ BaseRedfishHandler instantiated successfully")
        
    except Exception as e:
        print(f"❌ BaseRedfishHandler failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        print("Testing PostHandler import...")
        from handlers.post_handler import PostHandler
        print("✅ PostHandler imported successfully")
        
    except Exception as e:
        print(f"❌ PostHandler import failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    try:
        print("Testing PatchHandler import...")
        from handlers.patch_handler import PatchHandler
        print("✅ PatchHandler imported successfully")
        
    except Exception as e:
        print(f"❌ PatchHandler import failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        print("Testing PostHandler instantiation...")
        post_handler = PostHandler(request, ('127.0.0.1', 12345), server)
        print("✅ PostHandler instantiated successfully")
        
    except Exception as e:
        print(f"❌ PostHandler instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    try:
        print("Testing PatchHandler instantiation...")
        patch_handler = PatchHandler(request, ('127.0.0.1', 12345), server)
        print("✅ PatchHandler instantiated successfully")
        
    except Exception as e:
        print(f"❌ PatchHandler instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    try:
        print("Testing Multiple inheritance instantiation...")
        
        class TestMultipleHandler(PostHandler, PatchHandler):
            pass
        
        multi_handler = TestMultipleHandler(request, ('127.0.0.1', 12345), server)
        print("✅ Multiple inheritance instantiation successful")
        
        # Test property access
        print(f"post_log_entry_service: {multi_handler.post_log_entry_service}")
        print(f"log_entry_service: {multi_handler.log_entry_service}")
        
    except Exception as e:
        print(f"❌ Multiple inheritance failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    if test_individual_handlers():
        print("\n✅ All handler tests passed!")
    else:
        print("\n❌ Some handler tests failed!")