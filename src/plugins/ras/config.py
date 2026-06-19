"""
RAS Plugin Configuration

User-configurable settings for the RAS plugin, including parser selection.
"""

import os
from enum import Enum
from typing import Optional


class ParserType(Enum):
    """Available CPER/CPAD parser types."""
    AUTO = "auto"           # Auto-select best available (default)
    PYTHON = "python"       # Pure Python parser (no compilation)
    PYCPER = "pycper"       # Python bindings to C library (best performance)
    CLI = "cli"             # cper-convert command-line tool
    MOCK = "mock"           # Mock data (for testing without real files)


class RASConfig:
    """
    RAS Plugin configuration with multiple sources.
    
    Priority (highest to lowest):
    1. Runtime API parameters (passed directly to functions)
    2. Environment variables
    3. Configuration file (if implemented)
    4. Default values
    """
    
    # Default values
    DEFAULT_PARSER = ParserType.AUTO
    DEFAULT_PREFER_PYTHON = True  # For AUTO mode: prefer Python over C bindings
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        self._load_from_env()
    
    def _load_from_env(self):
        """Load configuration from environment variables."""
        # Parser type selection
        parser_env = os.getenv('RAS_PARSER_TYPE', '').lower()
        if parser_env:
            try:
                self.parser_type = ParserType(parser_env)
            except ValueError:
                self.parser_type = self.DEFAULT_PARSER
        else:
            self.parser_type = self.DEFAULT_PARSER
        
        # Prefer Python in AUTO mode?
        prefer_python_env = os.getenv('RAS_PREFER_PYTHON', '').lower()
        if prefer_python_env in ('1', 'true', 'yes'):
            self.prefer_python = True
        elif prefer_python_env in ('0', 'false', 'no'):
            self.prefer_python = False
        else:
            self.prefer_python = self.DEFAULT_PREFER_PYTHON
        
        # CPER/CPAD analysis settings
        self.verbose = os.getenv('RAS_VERBOSE', '').lower() in ('1', 'true', 'yes')
        self.mock_mode = os.getenv('RAS_MOCK_MODE', '').lower() in ('1', 'true', 'yes')
        

    
    def get_parser_type(self) -> ParserType:
        """Get the configured parser type."""
        return self.parser_type
    
    def should_prefer_python(self) -> bool:
        """Should AUTO mode prefer Python parser over C bindings?"""
        return self.prefer_python
    
    def __repr__(self) -> str:
        return (
            f"RASConfig(parser={self.parser_type.value}, "
            f"prefer_python={self.prefer_python}, "
            f"verbose={self.verbose}, "
            f"mock_mode={self.mock_mode})"
        )


# Global configuration instance
_config: Optional[RASConfig] = None


def get_config() -> RASConfig:
    """
    Get the global RAS configuration instance.
    
    Returns:
        RASConfig: Global configuration
    
    Example:
        >>> from src.plugins.ras.config import get_config
        >>> config = get_config()
        >>> print(config.parser_type)
    """
    global _config
    if _config is None:
        _config = RASConfig()
    return _config


def set_parser_type(parser: ParserType):
    """
    Set the parser type at runtime.
    
    Args:
        parser: Parser type to use
    
    Example:
        >>> from src.plugins.ras.config import set_parser_type, ParserType
        >>> set_parser_type(ParserType.PYTHON)  # Force Python parser
    """
    config = get_config()
    config.parser_type = parser


def reset_config():
    """Reset configuration to defaults (useful for testing)."""
    global _config
    _config = RASConfig()


# Convenience functions
def is_python_parser() -> bool:
    """Check if Python parser is configured."""
    return get_config().parser_type == ParserType.PYTHON


def is_auto_parser() -> bool:
    """Check if AUTO parser mode is configured."""
    return get_config().parser_type == ParserType.AUTO


if __name__ == '__main__':
    # Show current configuration
    config = get_config()
    print("=" * 70)
    print("RAS Plugin Configuration")
    print("=" * 70)
    print(f"\nParser Type:        {config.parser_type.value}")
    print(f"Prefer Python:      {config.prefer_python}")
    print(f"Verbose:            {config.verbose}")
    print(f"Mock Mode:          {config.mock_mode}")

    
    print("\n" + "=" * 70)
    print("Environment Variables")
    print("=" * 70)
    print("""
Set these environment variables to configure RAS plugin:

  RAS_PARSER_TYPE     Parser to use: auto|python|pycper|cli|mock
                      Default: auto
                      
  RAS_PREFER_PYTHON   In AUTO mode, prefer Python over C bindings
                      Values: 1|true|yes or 0|false|no
                      Default: true
                      
  RAS_VERBOSE         Enable verbose logging
                      Values: 1|true|yes or 0|false|no
                      Default: false
                      
  RAS_MOCK_MODE       Use mock data (no real parsing)
                      Values: 1|true|yes or 0|false|no
                      Default: false
                      


Examples:

  # Force Pure Python parser (no C library):
  export RAS_PARSER_TYPE=python
  
  # Force C bindings for best performance:
  export RAS_PARSER_TYPE=pycper
  
  # Auto-select, but prefer C bindings over Python:
  export RAS_PARSER_TYPE=auto
  export RAS_PREFER_PYTHON=false
  
  # Use mock data for testing:
  export RAS_MOCK_MODE=true
""")
