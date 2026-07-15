#!/bin/bash
# Tmux script to run RAS Plugin Demo with Event Listener
# This script starts all components needed for the RAS demo:
#   - BMC Server
#   - Event Listener
#   - RAS Demo

SESSION_NAME="ras-demo"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "❌ tmux is not installed. Please install it first:"
    echo "   sudo apt-get install tmux  # Ubuntu/Debian"
    echo "   sudo yum install tmux      # RHEL/CentOS"
    exit 1
fi

# Kill existing session if it exists
tmux has-session -t $SESSION_NAME 2>/dev/null
if [ $? -eq 0 ]; then
    echo "🔄 Killing existing session: $SESSION_NAME"
    tmux kill-session -t $SESSION_NAME
fi

echo "🚀 Starting RAS Demo in tmux session: $SESSION_NAME"
echo "   Project directory: $PROJECT_DIR"
echo ""

# Create new session with first window
cd "$PROJECT_DIR"
tmux new-session -d -s $SESSION_NAME -n "RAS-Demo"

# Configure panes
# Layout:
# +───────────────────┬───────────────────+
# |                   |                   |
# |  BMC Server       |                   |
# |  (pane 0)         |   RAS Demo       |
# |                   |   (pane 2)       |
# +───────────────────+                   |
# |                   |                   |
# |  Event Listener   |                   |
# |  (pane 1)         |                   |
# |                   |                   |
# +───────────────────┴───────────────────+

# Enable mouse support (scroll, pane select, resize)
tmux set-option -g mouse on

# Split into left/right, then split left into top/bottom
tmux split-window -h -t $SESSION_NAME:0.0
tmux split-window -v -t $SESSION_NAME:0.0

# Pane 0 (top-left): BMC Server
tmux send-keys -t $SESSION_NAME:0.0 "cd $PROJECT_DIR" C-m
tmux send-keys -t $SESSION_NAME:0.0 "clear" C-m
tmux send-keys -t $SESSION_NAME:0.0 "echo '═══════════════════════════════════════════'" C-m
tmux send-keys -t $SESSION_NAME:0.0 "echo '🖥️  BMC REDFISH SERVER (Port 8000)'" C-m
tmux send-keys -t $SESSION_NAME:0.0 "echo '═══════════════════════════════════════════'" C-m
tmux send-keys -t $SESSION_NAME:0.0 "echo 'Starting server...'" C-m
tmux send-keys -t $SESSION_NAME:0.0 "python3 -B servers/redfishMockupServer_platform.py -D mockups/ras_gen10 -p 8000" C-m

# Pane 1 (bottom-left): SDK Event Listener
tmux send-keys -t $SESSION_NAME:0.1 "cd $PROJECT_DIR" C-m
tmux send-keys -t $SESSION_NAME:0.1 "sleep 3" C-m
tmux send-keys -t $SESSION_NAME:0.1 "clear" C-m
tmux send-keys -t $SESSION_NAME:0.1 "echo '═══════════════════════════════════════════'" C-m
tmux send-keys -t $SESSION_NAME:0.1 "echo '🔔 SDK EVENT LISTENER (Port 8888)'" C-m
tmux send-keys -t $SESSION_NAME:0.1 "echo '═══════════════════════════════════════════'" C-m
tmux send-keys -t $SESSION_NAME:0.1 "echo 'Waiting for server...'" C-m
tmux send-keys -t $SESSION_NAME:0.1 "python3 examples/ras_api_demo/event_listener_sdk.py --port 8888 --bmc localhost:8000" C-m

# Pane 2 (right): RAS Demo
tmux send-keys -t $SESSION_NAME:0.2 "cd $PROJECT_DIR" C-m
tmux send-keys -t $SESSION_NAME:0.2 "clear" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo '═══════════════════════════════════════════'" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo '🧪 RAS DEMO'" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo '═══════════════════════════════════════════'" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo ''" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo 'Run full pipeline (reset + init + demo):'" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo '  python3 examples/ras_api_demo/reset_server.py --all && python3 examples/ras_api_demo/init_ras_api.py && python3 examples/ras_api_demo/ras_api_plugin_demo.py'" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo ''" C-m
tmux send-keys -t $SESSION_NAME:0.2 "echo 'Press UP arrow and ENTER when ready...'" C-m
# Run the demo, then pre-type (without Enter) the cleanup command so the user
# can tear down the tmux session by simply pressing Enter when finished.
tmux send-keys -t $SESSION_NAME:0.2 "python3 examples/ras_api_demo/reset_server.py --all && python3 examples/ras_api_demo/init_ras_api.py && python3 examples/ras_api_demo/ras_api_plugin_demo.py; tmux send-keys -t $SESSION_NAME:0.2 '$SCRIPT_DIR/cleanup_ras_demo.sh'" C-m

# Select the demo pane
tmux select-pane -t $SESSION_NAME:0.2

# Attach to session
echo ""
echo "✅ Tmux session created: $SESSION_NAME"
echo ""
echo "📖 Layout:"
echo "   ┌───────────────────┬───────────────────┐"
echo "   │  BMC Server       │                   │"
echo "   │  (Port 8000)      │  RAS Demo         │"
echo "   ├───────────────────┤  (Manual trigger) │"
echo "   │  Event Listener   │                   │"
echo "   │  (Port 8888)      │                   │"
echo "   └───────────────────┴───────────────────┘"
echo ""
echo "🎮 Controls:"
echo "   • Ctrl+B then arrow keys - Navigate between panes"
echo "   • Ctrl+B then [ - Scroll mode (q to exit)"
echo "   • Ctrl+B then d - Detach from session"
echo ""
echo "📝 To run the demo:"
echo "   1. Wait ~3 seconds for server and listener to start"
echo "   2. In the right pane, press UP arrow then ENTER"
echo "   3. Watch events appear in Event Listener pane (bottom-left)"
echo ""
echo "🔗 Reconnect later:"
echo "   tmux attach -t $SESSION_NAME"
echo ""
echo "❌ Stop everything:"
echo "   tmux kill-session -t $SESSION_NAME"
echo ""
echo "🧹 Clean up the terminal when done:"
echo "   $SCRIPT_DIR/cleanup_ras_demo.sh"
echo "   (When the demo finishes, this command is pre-typed in the demo pane —"
echo "    just press ENTER to run it.)"
echo ""
echo "Attaching to session in 2 seconds..."
sleep 2

tmux attach-session -t $SESSION_NAME
