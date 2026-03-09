# Parser Configuration: User vs Code-Level Options

## The Answer

**The parser choice is BOTH a user option AND a code-level option**, with a flexible priority system.

## Three Levels of Control

### 1️⃣ **User Control** (Environment Variables)

Users/operators can configure the parser **without changing code**:

```bash
# Force Pure Python parser (no compilation needed)
export RAS_PARSER_TYPE=python

# Force C bindings (best performance)
export RAS_PARSER_TYPE=pycper

# Auto-select, prefer Python
export RAS_PARSER_TYPE=auto
export RAS_PREFER_PYTHON=true

# Use mock data for testing
export RAS_MOCK_MODE=true
```

**When to use:**
- Production deployments (operations team decides)
- CI/CD pipelines (reproducible builds)
- Multi-tenant systems (per-user preferences)
- Testing environments

---

### 2️⃣ **Code-Level Control** (Function Parameters)

Developers can override configuration in code:

```python
from src.plugins.ras.unified_parser import parse_cper

# Respect user config (default)
data = parse_cper("error.cper")

# Force Python parser for this call
data = parse_cper("error.cper", prefer_python=True)

# Force C bindings for this call
data = parse_cper("error.cper", prefer_python=False)
```

**When to use:**
- Debugging specific parser issues
- Performance-critical code paths
- Testing different parsers
- API-specific requirements

---

### 3️⃣ **Runtime API** (Dynamic Configuration)

Change configuration at runtime:

```python
from src.plugins.ras.config import set_parser_type, ParserType

# Change for all subsequent calls
set_parser_type(ParserType.PYTHON)

# Now all parse calls use Python
data = parse_cper("error.cper")  # Uses Python
```

**When to use:**
- Dynamic system reconfiguration
- Feature flags / A/B testing
- Graceful fallback on errors
- Performance monitoring

---

## Configuration Priority

From **highest** to **lowest** priority:

```
1. CODE PARAMETERS           parse_cper(..., prefer_python=True)
   ↓ overrides
2. RUNTIME API CALLS         set_parser_type(ParserType.PYTHON)
   ↓ overrides
3. ENVIRONMENT VARIABLES     export RAS_PARSER_TYPE=python
   ↓ overrides
4. CONFIGURATION FILE        config.yaml (future)
   ↓ overrides
5. DEFAULT VALUES            auto, prefer_python=true
```

---

## Environment Variables Reference

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `RAS_PARSER_TYPE` | `auto`, `python`, `pycper`, `cli`, `mock` | `auto` | Which parser to use |
| `RAS_PREFER_PYTHON` | `true`, `false`, `1`, `0` | `true` | In AUTO mode, prefer Python? |
| `RAS_VERBOSE` | `true`, `false` | `false` | Enable verbose logging |
| `RAS_MOCK_MODE` | `true`, `false` | `false` | Use mock data |
| `RAS_POLICY_STRICT` | `true`, `false` | `false` | Strict policy enforcement |
| `RAS_MIN_CONFIDENCE` | `0-100` | `70` | Minimum confidence threshold |

---

## Real-World Usage Scenarios

### Scenario 1: Development (No C Compiler)
**User:** (no environment variables)  
**Code:** `parse_cper("error.cper")`  
**Result:** Pure Python parser (auto-detected)

### Scenario 2: Production BMC (C Library Built)
**User:** `export RAS_PARSER_TYPE=pycper`  
**Code:** `parse_cper("error.cper")`  
**Result:** C bindings (best performance)

### Scenario 3: CI/CD Testing (Reproducible)
**User:** `export RAS_PARSER_TYPE=python`  
**Code:** `parse_cper("error.cper")`  
**Result:** Pure Python (consistent across platforms)

### Scenario 4: Developer Debugging
**User:** (no environment variables)  
**Code:** `parse_cper("error.cper", prefer_python=True)`  
**Result:** Pure Python (easy to step through)

### Scenario 5: Performance-Critical Path
**User:** `export RAS_PARSER_TYPE=auto`  
**Code:** `parse_cper("error.cper", prefer_python=False)`  
**Result:** C bindings (code overrides auto mode)

---

## Quick Reference

### Check Current Configuration
```bash
python3 -m src.plugins.ras.config
```

### Test Different Configurations
```bash
# Test Python parser
RAS_PARSER_TYPE=python python3 -m src.plugins.ras.config

# Test C bindings
RAS_PARSER_TYPE=pycper python3 -m src.plugins.ras.config
```

### In Code
```python
from src.plugins.ras.config import get_config

config = get_config()
print(f"Using: {config.parser_type.value}")
print(f"Prefer Python: {config.prefer_python}")
```

---

## Files

- **[src/plugins/ras/config.py](../src/plugins/ras/config.py)** - Configuration system
- **[src/plugins/ras/unified_parser.py](../src/plugins/ras/unified_parser.py)** - Parser with config support
- **[examples/ras/demo_parser_config.py](../examples/ras/demo_parser_config.py)** - Configuration demo

---

## Summary

✅ **User Option:** Set `RAS_PARSER_TYPE` environment variable  
✅ **Code-Level Option:** Pass `prefer_python` parameter  
✅ **Runtime Option:** Use `set_parser_type()` API  
✅ **Auto-Detection:** Sensible defaults if nothing configured  
✅ **Priority System:** Code overrides user, user overrides defaults

**Best of both worlds:** Users control deployment, developers control edge cases!
