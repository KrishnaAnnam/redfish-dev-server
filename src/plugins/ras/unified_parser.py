"""
Three Ways to Parse CPER/CPAD in Python

This module demonstrates three alternative approaches to parsing CPER/CPAD files,
giving you flexibility based on your deployment needs.

Option 1: Pure Python Parser (NO COMPILATION NEEDED)
   - Works anywhere Python runs
   - No dependencies except standard library
   - Good performance for small-medium files
   - Best for: development, testing, cross-platform

Option 2: Python Bindings to C Library (pycper)
   - Must compile libcper first
   - Best performance
   - Direct memory access
   - Best for: production, high-volume processing

Option 3: Command-line Tool (cper-convert)
   - Must compile libcper first
   - Subprocess overhead
   - JSON conversion
   - Best for: scripts, batch processing
"""

import logging
from typing import Dict, Any, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)

# Import configuration
try:
    from .config import get_config, ParserType
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Try importing Python parser
try:
    from .cper_parser_python import PythonCPERParser, PythonCPADParser
    PYTHON_PARSER = True
except ImportError:
    PYTHON_PARSER = False
    logger.warning("Pure Python parser not available")

# Try importing Python bindings to C library
try:
    import pycper
    PYCPER_BINDINGS = True
except ImportError:
    PYCPER_BINDINGS = False
    logger.info("pycper bindings not available (libcper not built with Python support)")


class UnifiedCPERParser:
    """
    Unified CPER/CPAD parser with automatic fallback.
    
    Tries parsers in this order:
    1. Python bindings (pycper) - fastest if available
    2. Pure Python parser - no compilation needed
    3. Command-line tool - subprocess overhead
    
    Usage:
        parser = UnifiedCPERParser()
        data = parser.parse("error.cper")
    """
    
    def __init__(self, prefer_python: Optional[bool] = None, parser_type: Optional[str] = None):
        """
        Initialize unified parser.
        
        Args:
            prefer_python: If True, prefer pure Python parser over C bindings.
                          If None, uses config or default (True).
            parser_type: Force specific parser: 'auto', 'python', 'pycper', 'cli', 'mock'.
                        If None, uses config or default ('auto').
        """
        # Get configuration (user settings from env vars or config file)
        if CONFIG_AVAILABLE:
            config = get_config()
            self.prefer_python = prefer_python if prefer_python is not None else config.should_prefer_python()
            self.parser_type = parser_type if parser_type is not None else config.get_parser_type().value
        else:
            self.prefer_python = prefer_python if prefer_python is not None else True
            self.parser_type = parser_type if parser_type is not None else 'auto'
        
        # Initialize available parsers
        self.python_parser = None
        self.has_pycper = PYCPER_BINDINGS
        
        if PYTHON_PARSER:
            self.python_parser = PythonCPERParser()
            self.python_cpad_parser = PythonCPADParser()
            logger.info("✓ Pure Python parser available")
        
        if PYCPER_BINDINGS:
            logger.info("✓ pycper bindings available")
        
        # Determine which parser to use
        self._select_parser()
    
    def _select_parser(self):
        """Select the best available parser based on configuration."""
        # Check if user forced a specific parser type
        if self.parser_type == 'python':
            if self.python_parser:
                self.active_parser = "python"
                logger.info("Using: Pure Python parser (user configured)")
            else:
                logger.error("Python parser requested but not available")
                self.active_parser = "mock"
        
        elif self.parser_type == 'pycper':
            if self.has_pycper:
                self.active_parser = "pycper"
                logger.info("Using: pycper C bindings (user configured)")
            else:
                logger.error("pycper bindings requested but not available")
                self.active_parser = "mock"
        
        elif self.parser_type == 'mock':
            self.active_parser = "mock"
            logger.info("Using: Mock data (user configured)")
        
        else:  # 'auto' or any other value
            # Auto-select based on availability and preference
            if self.prefer_python and self.python_parser:
                self.active_parser = "python"
                logger.info("Using: Pure Python parser (auto-selected)")
            elif self.has_pycper:
                self.active_parser = "pycper"
                logger.info("Using: pycper C bindings (auto-selected)")
            elif self.python_parser:
                self.active_parser = "python"
                logger.info("Using: Pure Python parser (fallback)")
            else:
                self.active_parser = "mock"
                logger.warning("No parser available - will use mock data")
    
    def parse_cper(self, source: Union[str, Path, bytes]) -> Dict[str, Any]:
        """
        Parse CPER from file or bytes.
        
        Args:
            source: File path or bytes object
            
        Returns:
            dict: Parsed CPER data
        """
        if self.active_parser == "python":
            return self._parse_with_python(source, is_cpad=False)
        elif self.active_parser == "pycper":
            return self._parse_with_pycper(source, is_cpad=False)
        else:
            return self._create_mock_cper()
    
    def parse_cpad(self, source: Union[str, Path, bytes]) -> Dict[str, Any]:
        """
        Parse CPAD from file or bytes.
        
        Args:
            source: File path or bytes object
            
        Returns:
            dict: Parsed CPAD data
        """
        if self.active_parser == "python":
            return self._parse_with_python(source, is_cpad=True)
        elif self.active_parser == "pycper":
            return self._parse_with_pycper(source, is_cpad=True)
        else:
            return self._create_mock_cpad()
    
    def _parse_with_python(self, source: Union[str, Path, bytes], is_cpad: bool) -> Dict[str, Any]:
        """Parse using pure Python parser."""
        try:
            if isinstance(source, bytes):
                if is_cpad:
                    return self.python_cpad_parser.parse_cpad_bytes(source)
                else:
                    return self.python_parser.parse_cper_bytes(source)
            else:
                if is_cpad:
                    return self.python_cpad_parser.parse_cpad_file(str(source))
                else:
                    return self.python_parser.parse_cper_file(str(source))
        except Exception as e:
            logger.error(f"Python parser failed: {e}")
            raise
    
    def _parse_with_pycper(self, source: Union[str, Path, bytes], is_cpad: bool) -> Dict[str, Any]:
        """Parse using pycper C bindings."""
        try:
            # Read bytes if file path
            if isinstance(source, (str, Path)):
                with open(source, 'rb') as f:
                    data = f.read()
            else:
                data = source
            
            # Use pycper bindings
            result = pycper.parse(data)
            return result
            
        except Exception as e:
            logger.error(f"pycper bindings failed: {e}")
            raise
    
    def _create_mock_cper(self) -> Dict[str, Any]:
        """Create mock CPER data."""
        return {
            "mock": True,
            "header": {
                "signatureStart": "CPER",
                "sectionCount": 1,
                "errorSeverity": 2,
            },
            "sections": [
                {
                    "sectionType": "Platform Memory",
                    "sectionSeverity": 2,
                }
            ]
        }
    
    def _create_mock_cpad(self) -> Dict[str, Any]:
        """Create mock CPAD data."""
        return {
            "mock": True,
            "header": {
                "signature": "CPAD",
                "actionName": "Memory Error Spoof",
            },
            "payload": {
                "action": "spoof",
            }
        }


# Convenience functions
def parse_cper(source: Union[str, Path, bytes], prefer_python: Optional[bool] = None) -> Dict[str, Any]:
    """
    Parse CPER using best available method.
    
    Respects user configuration from environment variables or config.
    
    Args:
        source: File path or bytes
        prefer_python: Override preference for pure Python over C bindings.
                      If None, uses config (default: True)
        
    Returns:
        dict: Parsed CPER data
    
    Example:
        # Use configured parser (from RAS_PARSER_TYPE env var or default)
        data = parse_cper("error.cper")
        
        # Force Python parser regardless of config
        data = parse_cper("error.cper", prefer_python=True)
        
        # From bytes
        with open("error.cper", "rb") as f:
            data = parse_cper(f.read())
    """
    parser = UnifiedCPERParser(prefer_python=prefer_python)
    return parser.parse_cper(source)


def parse_cpad(source: Union[str, Path, bytes], prefer_python: Optional[bool] = None) -> Dict[str, Any]:
    """
    Parse CPAD using best available method.
    
    Respects user configuration from environment variables or config.
    
    Args:
        source: File path or bytes
        prefer_python: Override preference for pure Python over C bindings.
                      If None, uses config (default: True)
        
    Returns:
        dict: Parsed CPAD data
    
    Example:
        # Use configured parser (from RAS_PARSER_TYPE env var or default)
        data = parse_cpad("action.cpad")
        
        # Force C bindings regardless of config
        data = parse_cpad("action.cpad", prefer_python=False)
        
        # From bytes
        with open("action.cpad", "rb") as f:
            data = parse_cpad(f.read())
    """
    parser = UnifiedCPERParser(prefer_python=prefer_python)
    return parser.parse_cpad(source)


if __name__ == '__main__':
    import sys
    
    # Demo: show which parsers are available
    print("═" * 70)
    print("CPER/CPAD Parser Availability Check")
    print("═" * 70)
    
    print(f"\n1. Pure Python Parser:  {'✓ Available' if PYTHON_PARSER else '✗ Not available'}")
    print("   - No compilation needed")
    print("   - Works on any platform")
    print("   - Good for development/testing")
    
    print(f"\n2. pycper C Bindings:   {'✓ Available' if PYCPER_BINDINGS else '✗ Not available'}")
    print("   - Requires: ./build_libcper.sh --with-python")
    print("   - Best performance")
    print("   - Direct memory access")
    
    print(f"\n3. cper-convert Tool:   {'✓ Available' if Path('src/plugins/ras/libcper/build/cper-convert').exists() else '✗ Not available'}")
    print("   - Requires: ./build_libcper.sh")
    print("   - Command-line utility")
    print("   - Good for scripting")
    
    print("\n" + "═" * 70)
    print(f"Recommended: {'Pure Python' if PYTHON_PARSER else 'Build libcper'}")
    print("═" * 70)
    
    # Test if file provided
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(f"\nParsing: {file_path}")
        
        try:
            if file_path.endswith('.cper'):
                result = parse_cper(file_path)
            elif file_path.endswith('.cpad'):
                result = parse_cpad(file_path)
            else:
                print("Unknown file type")
                sys.exit(1)
            
            import json
            print(json.dumps(result, indent=2))
            
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
