#!/bin/bash
#
# Set up external dependencies for the RAS API demo
#
# Handles both dependencies:
#   - redfish-client-sdk: cloned from GitHub, installed as a pip package
#   - libcper: cloned from GitHub, built with meson/ninja
#
# Usage:
#   bash setup_dependencies.sh             # Fetch + install both
#   bash setup_dependencies.sh --sdk       # SDK only
#   bash setup_dependencies.sh --libcper   # libcper only
#   bash setup_dependencies.sh --update    # Update both to latest
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# SDK config
SDK_DIR="$PROJECT_ROOT/redfish_client_sdk"
SDK_REPO="https://github.com/harira-microsoft/redfish-client-sdk.git"
SDK_BRANCH="main"

# libcper config
LIBCPER_DIR="$PROJECT_ROOT/src/plugins/ras/libcper"
LIBCPER_REPO="https://github.com/dwalton64/libcper.git"
LIBCPER_BRANCH="main"

# ============================================================
# SDK functions
# ============================================================

fetch_sdk() {
    if [ -d "$SDK_DIR" ] && [ -d "$SDK_DIR/.git" ]; then
        echo "✅ redfish-client-sdk already present at $SDK_DIR"
        return
    fi

    echo "📥 Fetching redfish-client-sdk from $SDK_REPO..."
    git clone --depth 1 -b "$SDK_BRANCH" "$SDK_REPO" "$SDK_DIR"
    echo "✅ redfish-client-sdk fetched successfully!"
    echo ""
}

install_sdk() {
    if [ ! -d "$SDK_DIR/python" ]; then
        echo "❌ SDK python directory not found. Run fetch first."
        return 1
    fi

    echo "📦 Installing redfish-client-sdk..."
    pip install "$SDK_DIR/python/"
    echo "✅ redfish-client-sdk installed!"
    echo ""
}

update_sdk() {
    if [ -d "$SDK_DIR/.git" ]; then
        echo "🔄 Updating redfish-client-sdk to latest..."
        cd "$SDK_DIR"
        git pull origin "$SDK_BRANCH"
        cd "$PROJECT_ROOT"
        install_sdk
        echo "✅ redfish-client-sdk updated!"
    else
        echo "⚠️  SDK not found, fetching fresh..."
        fetch_sdk
        install_sdk
    fi
    echo ""
}

# ============================================================
# libcper functions
# ============================================================

fetch_libcper() {
    if [ -d "$LIBCPER_DIR" ] && [ -d "$LIBCPER_DIR/.git" ]; then
        echo "✅ libcper already present at $LIBCPER_DIR"
        return
    fi

    echo "📥 Fetching libcper from $LIBCPER_REPO..."
    git clone --depth 1 -b "$LIBCPER_BRANCH" "$LIBCPER_REPO" "$LIBCPER_DIR"
    echo "✅ libcper fetched successfully!"
    echo ""
}

build_libcper() {
    if [ ! -d "$LIBCPER_DIR" ]; then
        echo "❌ libcper directory not found. Run fetch first."
        return 1
    fi

    # Check if already built
    if [ -f "$LIBCPER_DIR/build/cper-convert" ] && [ -f "$LIBCPER_DIR/build/cpad-convert" ]; then
        echo "✅ libcper already built (cper-convert and cpad-convert present)"
        return
    fi

    echo "🔨 Building libcper with meson/ninja..."

    # Check prerequisites
    if ! command -v meson &> /dev/null; then
        echo "❌ meson not found. Install with: sudo apt install meson"
        return 1
    fi
    if ! command -v ninja &> /dev/null; then
        echo "❌ ninja not found. Install with: sudo apt install ninja-build"
        return 1
    fi

    cd "$LIBCPER_DIR"
    if [ ! -d "build" ]; then
        meson setup build
    fi
    ninja -C build
    cd "$PROJECT_ROOT"

    echo "✅ libcper built! Binaries at $LIBCPER_DIR/build/"
    echo ""
}

update_libcper() {
    if [ -d "$LIBCPER_DIR/.git" ]; then
        echo "🔄 Updating libcper to latest..."
        cd "$LIBCPER_DIR"
        git pull origin "$LIBCPER_BRANCH"
        cd "$PROJECT_ROOT"
        # Rebuild after update
        rm -rf "$LIBCPER_DIR/build"
        build_libcper
        echo "✅ libcper updated and rebuilt!"
    else
        echo "⚠️  libcper not found, fetching fresh..."
        fetch_libcper
        build_libcper
    fi
    echo ""
}

# ============================================================
# Main
# ============================================================

echo "========================================"
echo "RAS API Demo - Dependency Setup"
echo "========================================"
echo ""

case "${1:-}" in
    --sdk)
        fetch_sdk
        install_sdk
        ;;
    --libcper)
        fetch_libcper
        build_libcper
        ;;
    --update)
        update_sdk
        update_libcper
        ;;
    *)
        fetch_sdk
        install_sdk
        fetch_libcper
        build_libcper
        ;;
esac

echo "========================================"
echo "✅ Setup complete!"
echo ""
echo "Run the demo:"
echo "   bash examples/ras_api_demo/run_ras_demo.sh"
echo ""
echo "Or run manually:"
echo "   python3 servers/redfishMockupServer_platform.py -D mockups/ras_gen10 -p 8000"
echo "   python3 examples/ras_api_demo/event_listener_sdk.py --port 8888 --bmc localhost:8000"
echo "   python3 examples/ras_api_demo/ras_api_plugin_demo.py"
echo "========================================"
