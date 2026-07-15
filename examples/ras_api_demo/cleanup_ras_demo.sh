#!/bin/bash
# Cleanup script for the RAS Plugin Demo.
# Cleanly tears down the tmux session created by run_ras_demo.sh and reaps any
# orphaned demo processes (BMC server / event listener) that may still be
# holding their ports.
#
# Safe to run at any time: if nothing is running it simply reports that there
# was nothing to clean up.

SESSION_NAME="ras-demo"

# Exact script names launched by run_ras_demo.sh. Matching these specifically
# (rather than a broad "python3" pattern) ensures we never touch unrelated
# Python processes on the machine.
SERVER_SCRIPT="redfishMockupServer_platform.py"
LISTENER_SCRIPT="event_listener_sdk.py"

# Ports the demo binds, used as a secondary confirmation when reaping orphans.
DEMO_PORTS=(8000 8888)

did_something=0

echo "🧹 Cleaning up the RAS demo terminal..."
echo "   This will:"
echo "     • Close the tmux demo windows (the split-pane layout)"
echo "     • Stop all processes started for the demo (BMC server, event listener)"
echo "     • Return you to a clean terminal"
echo ""

# 1. Kill the tmux session. This tears down the split-pane UI and normally
#    terminates the child processes running inside its panes.
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "   • Killing tmux session: $SESSION_NAME"
    tmux kill-session -t "$SESSION_NAME"
    did_something=1
else
    echo "   • No tmux session named '$SESSION_NAME' found."
fi

# 2. Fallback: reap any orphaned demo processes that survived (e.g. detached
#    from their pane, or started outside tmux). Scoped tightly to the demo's
#    own script names so nothing unrelated is affected.
reap_by_name() {
    local script="$1"
    # -f matches against the full command line; the script name is specific
    # enough that this will not match unrelated processes.
    local pids
    pids=$(pgrep -f "$script" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "   • Stopping leftover process(es) for $script: $pids"
        # shellcheck disable=SC2086
        kill $pids 2>/dev/null
        did_something=1
    fi
}

reap_by_name "$SERVER_SCRIPT"
reap_by_name "$LISTENER_SCRIPT"

# 3. Last-resort safety net: if something is still bound to a demo port, report
#    it so the user can act. We only kill a PID here if it is one of our known
#    demo scripts, to avoid taking down an unrelated app on the same port.
if command -v lsof &>/dev/null; then
    for port in "${DEMO_PORTS[@]}"; do
        pids=$(lsof -ti ":$port" 2>/dev/null)
        for pid in $pids; do
            cmd=$(ps -p "$pid" -o args= 2>/dev/null)
            if echo "$cmd" | grep -qE "$SERVER_SCRIPT|$LISTENER_SCRIPT"; then
                echo "   • Freeing port $port (demo process PID $pid)"
                kill "$pid" 2>/dev/null
                did_something=1
            elif [ -n "$cmd" ]; then
                echo "   ⚠️  Port $port is held by a non-demo process (PID $pid): $cmd"
                echo "      Leaving it untouched."
            fi
        done
    done
fi

if [ "$did_something" -eq 1 ]; then
    echo "✅ RAS demo cleaned up."
else
    echo "✅ Nothing to clean up."
fi
