#!/bin/bash
#
# Set up the Redfish Client SDK for the RAS API demo
#
# The SDK provides the RedfishEventListener used by event_listener_sdk.py
# Repo: https://github.com/harira-microsoft/redfish-client-sdk
#
# Usage:
#   ./examples/ras_api_demo/setup.sh           # Fetch + install SDK
#   ./examples/ras_api_demo/setup.sh --update  # Update to latest
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SDK_DIR="$PROJECT_ROOT/redfish_client_sdk"
SDK_REPO="https://github.com/harira-microsoft/redfish-client-sdk.git"
SDK_BRANCH="main"

fetch_sdk() {
    if [ -d "$SDK_DIR" ] && [ -d "$SDK_DIR/.git" ]; then
        echo "✅ redfish-client-sdk already present at $SDK_DIR"
        return
    fi

    echo "📥 Fetching redfish-client-sdk from $SDK_REPO..."
    git clone --depth 1 -b "$SDK_BRANCH" "$SDK_REPO" "$SDK_DIR"
    echo "✅ redfish-client-sdk fetched successfully!"
}

install_sdk() {
    if [ ! -d "$SDK_DIR/python" ]; then
        echo "❌ SDK python directory not found. Run without --update first."
        exit 1
    fi

    echo "📦 Installing redfish-client-sdk..."
    pip install "$SDK_DIR/python/"
    echo "✅ SDK installed!"
}

update_sdk() {
    if [ -d "$SDK_DIR" ] && [ -d "$SDK_DIR/.git" ]; then
        echo "🔄 Updating redfish-client-sdk..."
        cd "$SDK_DIR" && git pull origin "$SDK_BRANCH" && cd -
    else
        fetch_sdk
    fi
    install_sdk
}

# Main
echo "========================================"
echo "RAS API Demo - SDK Setup"
echo "========================================"
echo ""

case "${1:-}" in
    --update)
        update_sdk
        ;;
    *)
        fetch_sdk
        install_sdk
        ;;
esac

echo ""
echo "✅ Setup complete! You can now run the demo:"
echo "   python examples/ras_api_demo/ras_api_plugin_demo.py"
