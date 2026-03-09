#!/bin/bash
# Quick Start Script for BMC Redfish Simulator Web UIs

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   BMC Redfish Simulator - Web UI Quick Start                ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check if we're in the right directory
if [ ! -f "webui/requirements_webui.txt" ]; then
    echo "❌ Error: Please run this script from the bmc-redfish-simulator root directory"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    exit 1
fi

echo "📦 Installing Web UI dependencies..."
pip3 install -r webui/requirements_webui.txt

if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi

echo ""
echo "✅ Dependencies installed successfully!"
echo ""
echo "🚀 Choose an option:"
echo ""
echo "  1. Launch Server Web UI (port 5000)"
echo "  2. Launch Client Web UI (port 5001)"
echo "  3. Launch Both (Recommended)"
echo ""

read -p "Enter your choice (1-3): " choice

case $choice in
    1)
        echo ""
        echo "🖥️  Starting Server Web UI..."
        echo "   Access at: http://127.0.0.1:5000/"
        echo ""
        python3 webui/webui_launcher.py server
        ;;
    2)
        echo ""
        echo "🔌 Starting Client Web UI..."
        echo "   Access at: http://127.0.0.1:5001/"
        echo ""
        python3 webui/webui_launcher.py client
        ;;
    3)
        echo ""
        echo "🚀 Starting both Web UIs..."
        echo "   Server UI: http://127.0.0.1:5000/"
        echo "   Client UI: http://127.0.0.1:5001/"
        echo ""
        python3 webui/webui_launcher.py both
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac
