#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Minimal test to reproduce the property conflict issue
"""

class MockServer:
    def __init__(self):
        self.config = {}

class MockConfig:
    pass

class BaseHandler:
    def __init__(self, request=None, client_address=None, server=None):
        self.server = server or MockServer()

class PostHandler(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log_entry_service_post = None
    
    @property
    def post_log_entry_service(self):
        if self._log_entry_service_post is None:
            self._log_entry_service_post = "POST_LOG_SERVICE"
        return self._log_entry_service_post
    
    @post_log_entry_service.setter
    def post_log_entry_service(self, value):
        self._log_entry_service_post = value

class PatchHandler(BaseHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log_entry_service = None
    
    @property
    def log_entry_service(self):
        if self._log_entry_service is None:
            self._log_entry_service = "PATCH_LOG_SERVICE"
        return self._log_entry_service
    
    @log_entry_service.setter
    def log_entry_service(self, value):
        self._log_entry_service = value

class MainHandler(PostHandler, PatchHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

def test_property_conflict():
    print("Testing minimal property conflict reproduction...")
    
    try:
        print("Creating PostHandler...")
        post = PostHandler()
        print(f"✅ PostHandler.post_log_entry_service: {post.post_log_entry_service}")
        
        print("Creating PatchHandler...")
        patch = PatchHandler()
        print(f"✅ PatchHandler.log_entry_service: {patch.log_entry_service}")
        
        print("Creating MainHandler with multiple inheritance...")
        main = MainHandler()
        print(f"✅ MainHandler.post_log_entry_service: {main.post_log_entry_service}")
        print(f"✅ MainHandler.log_entry_service: {main.log_entry_service}")
        
        print("✅ All tests passed - no property conflict!")
        
    except Exception as e:
        print(f"❌ Property conflict reproduced: {e}")
        import traceback
        traceback.print_exc()
        
        # Print MRO for debugging
        print(f"\nMRO: {MainHandler.__mro__}")
        
        # Check if properties exist
        print(f"MainHandler has log_entry_service: {'log_entry_service' in MainHandler.__dict__}")
        print(f"PatchHandler has log_entry_service: {'log_entry_service' in PatchHandler.__dict__}")
        print(f"PostHandler has post_log_entry_service: {'post_log_entry_service' in PostHandler.__dict__}")

if __name__ == "__main__":
    test_property_conflict()