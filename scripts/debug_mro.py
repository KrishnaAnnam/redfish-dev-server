#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE.md in the project root for license information.
"""
Debug script to check Method Resolution Order (MRO) conflicts
"""
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from handlers.get_handler import GetHandler
from handlers.post_handler import PostHandler
from handlers.patch_handler import PatchHandler
from handlers.put_handler import PutHandler
from handlers.delete_handler import DeleteHandler
from handlers.main_handler import RedfishMockupHandler

print("Method Resolution Order for RedfishMockupHandler:")
print("=" * 50)

for i, cls in enumerate(RedfishMockupHandler.__mro__):
    print(f"{i+1}. {cls.__name__} ({cls.__module__})")

print("\nChecking for property conflicts:")
print("=" * 50)

# Check properties in each class
for cls in RedfishMockupHandler.__mro__:
    if hasattr(cls, '__dict__'):
        props = [name for name, obj in cls.__dict__.items() 
                if isinstance(obj, property)]
        if props:
            print(f"{cls.__name__}: {props}")

print("\nChecking for log_entry_service property specifically:")
print("=" * 50)

for cls in RedfishMockupHandler.__mro__:
    if hasattr(cls, '__dict__') and 'log_entry_service' in cls.__dict__:
        prop = cls.__dict__['log_entry_service']
        print(f"{cls.__name__}.log_entry_service: {type(prop)} - {prop}")
        if isinstance(prop, property):
            print(f"  - getter: {prop.fget}")
            print(f"  - setter: {prop.fset}")
            print(f"  - deleter: {prop.fdel}")

print("\nChecking for post_log_entry_service property:")
print("=" * 50)

for cls in RedfishMockupHandler.__mro__:
    if hasattr(cls, '__dict__') and 'post_log_entry_service' in cls.__dict__:
        prop = cls.__dict__['post_log_entry_service']
        print(f"{cls.__name__}.post_log_entry_service: {type(prop)} - {prop}")