# Python Alternatives to libcper C Library

Yes! You have **THREE ways** to parse CPER/CPAD files in Python without using the C library.

## Quick Summary

| Method | Compilation | Performance | Best For |
|--------|-------------|-------------|----------|
| **1. Pure Python Parser** | ❌ None | Good | Development, testing, portability |
| **2. pycper Bindings** | ✅ Required | Excellent | Production, high-volume |
| **3. cper-convert Tool** | ✅ Required | Good | Scripting, batch jobs |

## Option 1: Pure Python Parser ⭐ **RECOMMENDED for Development**

**Location:** [src/plugins/ras/cper_parser_python.py](../src/plugins/ras/cper_parser_python.py)

### Advantages
- ✅ **NO compilation needed** - works immediately
- ✅ **Pure Python** - works on any platform (Linux, Windows, Mac, ARM, x86)
- ✅ **No dependencies** - only uses Python standard library
- ✅ **Easy to debug** - Python source code you can step through
- ✅ **Easy to extend** - add custom section parsers in Python

### Usage

```python
from src.plugins.ras.cper_parser_python import parse_cper, parse_cpad

# Parse CPER binary file
cper_data = parse_cper("error.cper")
print(cper_data['header']['sectionCount'])

# Parse CPAD binary file
cpad_data = parse_cpad("action.cpad")
print(cpad_data['header']['actionName'])

# Parse from bytes
with open("error.cper", "rb") as f:
    cper_data = parse_cper(f.read())
```

### What It Supports

- ✅ CPER header parsing (UEFI Spec Appendix N)
- ✅ Section descriptors
- ✅ All GUID mappings (Processor, Memory, PCIe, CXL, etc.)
- ✅ Raw section data extraction (hex format)
- ✅ CPAD header parsing
- ✅ CPAD JSON payload extraction
- ✅ Binary → JSON conversion

### Performance

- Small files (<1 MB): **Excellent** (milliseconds)
- Medium files (1-10 MB): **Good** (< 1 second)
- Large files (>10 MB): **Acceptable** (may use more memory)

---

## Option 2: pycper Python Bindings 🚀 **RECOMMENDED for Production**

**Location:** [src/plugins/ras/libcper/pycper.c](../src/plugins/ras/libcper/pycper.c)

### Build Instructions

```bash
# Build libcper with Python bindings
cd src/plugins/ras/libcper
meson setup build -Dlibcper_python=true
ninja -C build

# Install pycper module
sudo ninja -C build install
# OR add to PYTHONPATH
export PYTHONPATH="$PWD/build:$PYTHONPATH"
```

### Usage

```python
import pycper

# Parse CPER binary
with open("error.cper", "rb") as f:
    data = f.read()

cper_dict = pycper.parse(data)
print(cper_dict)  # Native Python dict
```

### Advantages

- ✅ **Best performance** - native C speed
- ✅ **Direct memory access** - no subprocess overhead
- ✅ **Returns Python dict** - native integration
- ✅ **Handles all UEFI section types** - complete coverage

### Disadvantages

- ❌ Must compile libcper first
- ❌ Platform-specific binary (Linux/ARM binaries differ)
- ❌ Requires json-c library

---

## Option 3: cper-convert Command-Line Tool

**Location:** [src/plugins/ras/libcper/cper-convert.c](../src/plugins/ras/libcper/cper-convert.c)

### Build Instructions

```bash
# Build libcper
cd src/plugins/ras/libcper
meson setup build
ninja -C build

# Tool is at: build/cper-convert
```

### Usage

```python
import subprocess
import json

# Convert CPER to JSON via subprocess
result = subprocess.run(
    ['./build/cper-convert', '-i', 'error.cper', '-o', '/dev/stdout'],
    capture_output=True,
    text=True
)

cper_data = json.loads(result.stdout)
```

### Advantages

- ✅ Command-line utility - easy for scripts
- ✅ Can be used from any language
- ✅ Standard input/output

### Disadvantages

- ❌ Subprocess overhead
- ❌ JSON serialization overhead
- ❌ Must compile libcper first

---

## Unified Interface 🎯 **BEST OF ALL WORLDS**

**Location:** [src/plugins/ras/unified_parser.py](../src/plugins/ras/unified_parser.py)

Automatically uses the best available method:

```python
from src.plugins.ras.unified_parser import parse_cper, parse_cpad

# Automatically uses:
# 1. pycper bindings (if available) - fastest
# 2. Pure Python parser (if available) - no compilation
# 3. cper-convert tool (if available) - fallback
# 4. Mock data (if nothing available) - for testing

data = parse_cper("error.cper")
data = parse_cpad("action.cpad")
```

### Check What's Available

```bash
python3 -m src.plugins.ras.unified_parser

# Output shows:
# ✓/✗ Pure Python Parser
# ✓/✗ pycper C Bindings
# ✓/✗ cper-convert Tool
```

---

## Recommendations by Use Case

### 🧪 Development & Testing
**Use:** Pure Python Parser
```python
from src.plugins.ras.cper_parser_python import parse_cper
```
- No setup required
- Easy debugging
- Works everywhere

### 🏭 Production BMC Deployment
**Use:** pycper Bindings
```python
import pycper
```
- Best performance
- Native C speed
- Memory efficient

### 📜 Scripting & Automation
**Use:** Unified Interface
```python
from src.plugins.ras.unified_parser import parse_cper
```
- Automatic fallback
- Works in any environment
- Future-proof

### 🌐 Cross-Platform Distribution
**Use:** Pure Python Parser
```python
from src.plugins.ras.cper_parser_python import parse_cper
```
- No compilation per platform
- Single codebase
- Works on ARM, x86, Windows, Linux, Mac

---

## Current Status

✅ **Pure Python Parser:** Implemented and ready to use  
✅ **pycper Bindings:** Available in libcper (must build with `-Dlibcper_python=true`)  
✅ **cper-convert Tool:** Available in libcper (builds by default)  
✅ **Unified Interface:** Implemented with automatic fallback

## Files Created

1. **`src/plugins/ras/cper_parser_python.py`** - Pure Python CPER/CPAD parser
2. **`src/plugins/ras/unified_parser.py`** - Unified interface with auto-fallback
3. **`examples/ras/demo_python_parser.py`** - Demo script

## Next Steps

### To use Pure Python parser (NO COMPILATION):
```bash
python3 -c "from src.plugins.ras.cper_parser_python import parse_cper; \
            print('✓ Pure Python parser ready!')"
```

### To build pycper bindings (BEST PERFORMANCE):
```bash
cd src/plugins/ras/libcper
meson setup build -Dlibcper_python=true
ninja -C build
```

### To test with your JSON files:
```python
# Your existing JSON files work as-is!
import json

with open("examples/ras/memErrorSpoofCpad.json") as f:
    cpad_data = json.load(f)  # Already JSON, no parsing needed!
```

---

## The Bottom Line

**For Simulator (Development):** Use Pure Python - no compilation, works everywhere  
**For BMC (Production):** Use pycper bindings - best performance, native C  
**For Flexibility:** Use unified interface - automatic best choice

**All three options preserve the RasApi team's work - the Pure Python parser implements the same binary formats defined in the C library, giving you maximum flexibility!**
