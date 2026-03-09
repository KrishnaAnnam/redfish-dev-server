#!/bin/bash
#
# Build libcper C library for CPER/CPAD processing
#
# This script builds the libcper library which provides:
# - Binary CPER parsing (UEFI Common Platform Error Records)
# - Binary CPAD parsing (Common Platform Action Descriptors)
# - cper-convert and cpad-convert CLI tools
# - Optional Python bindings (pycper module)
#
# The libcper library is maintained at: https://github.com/dwalton64/libcper
# It is included as a git submodule and will be fetched automatically.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBCPER_DIR="$SCRIPT_DIR/src/plugins/ras/libcper"
LIBCPER_REPO="https://github.com/dwalton64/libcper.git"

echo "========================================"
echo "Building libcper for RAS Plugin"
echo "========================================"
echo ""

# Function to fetch libcper if not present
fetch_libcper() {
    echo "📥 Fetching libcper from $LIBCPER_REPO..."
    
    # Check if we're in a git repository
    if [ -d "$SCRIPT_DIR/.git" ]; then
        # Try submodule approach first
        cd "$SCRIPT_DIR"
        
        # Check if submodule is configured
        if git config --file .gitmodules --get submodule.src/plugins/ras/libcper.url &>/dev/null; then
            echo "   Initializing git submodule..."
            git submodule update --init --recursive src/plugins/ras/libcper
        else
            # Submodule not configured, clone directly
            echo "   Cloning repository..."
            git clone --depth 1 "$LIBCPER_REPO" "$LIBCPER_DIR"
        fi
    else
        # Not a git repo, just clone
        echo "   Cloning repository..."
        git clone --depth 1 "$LIBCPER_REPO" "$LIBCPER_DIR"
    fi
    
    echo "✅ libcper fetched successfully!"
    echo ""
}

# Check if libcper directory exists and has content
if [ ! -d "$LIBCPER_DIR" ] || [ ! -f "$LIBCPER_DIR/meson.build" ]; then
    echo "📦 libcper not found locally, fetching from upstream..."
    echo ""
    fetch_libcper
fi

# Optionally update to latest version
if [ "$1" == "--update" ] || [ "$1" == "-u" ]; then
    echo "🔄 Updating libcper to latest version..."
    cd "$SCRIPT_DIR"
    if git config --file .gitmodules --get submodule.src/plugins/ras/libcper.url &>/dev/null; then
        git submodule update --remote src/plugins/ras/libcper
    else
        cd "$LIBCPER_DIR"
        git pull origin main
    fi
    echo "✅ Updated to latest version!"
    echo ""
fi

cd "$LIBCPER_DIR"

# Check for meson
if ! command -v meson &> /dev/null; then
    echo "❌ Error: meson not found"
    echo ""
    echo "Install meson:"
    echo "  Ubuntu/Debian: sudo apt install meson ninja-build"
    echo "  Fedora/RHEL:   sudo dnf install meson ninja-build"
    echo "  macOS:         brew install meson ninja"
    exit 1
fi

# Check for json-c library
if ! pkg-config --exists json-c; then
    echo "⚠️  Warning: json-c library not found"
    echo ""
    echo "Install json-c:"
    echo "  Ubuntu/Debian: sudo apt install libjson-c-dev"
    echo "  Fedora/RHEL:   sudo dnf install json-c-devel"
    echo "  macOS:         brew install json-c"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "📦 Setting up build directory..."
meson setup build --wipe || meson setup build

echo ""
echo "🔨 Building libcper..."
ninja -C build

echo ""
echo "✅ Build complete!"
echo ""
echo "Built artifacts:"
echo "  📚 Library:      build/libcper.so (or .dylib/.a)"
echo "  🔧 CLI Tools:    build/cper-convert"
echo "                   build/cpad-convert"
echo ""
echo "Test the build:"
echo "  cd $LIBCPER_DIR"
echo "  ./build/cper-convert --help"
echo ""
echo "Optional: Install system-wide (requires sudo):"
echo "  sudo ninja -C build install"
echo ""
echo "Optional: Build Python bindings:"
echo "  meson setup build -Dpython=enabled --wipe"
echo "  ninja -C build"
echo "  pip install build/pycper*.whl"
echo ""
echo "The RAS plugin will now automatically use the built library!"
echo ""
echo "Script options:"
echo "  ./build_libcper.sh           # Build (auto-fetches if needed)"
echo "  ./build_libcper.sh --update  # Update to latest and build"
echo "========================================"
