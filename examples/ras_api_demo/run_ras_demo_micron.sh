#!/bin/bash
# Launch the RAS API demo with Micron DIMMs and the MERC analyzer.

set -u

SESSION_NAME="ras-demo"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
MICRON_TEMPLATE="$PROJECT_DIR/mockups/ras_gen1/ras_endpoint_config_micron.json"

usage() {
    echo "Usage: $0 <merc-retry-read.csv>"
    echo ""
    echo "The CSV must contain:"
    echo "  msn,mpn,rr_log,rr_addr1,rr_addr2,rr_parity,intel_hw_gen"
}

if [ "$#" -ne 1 ]; then
    usage >&2
    exit 2
fi

if ! command -v tmux &>/dev/null; then
    echo "tmux is not installed. Install it with: sudo apt-get install tmux" >&2
    exit 1
fi

if ! command -v realpath &>/dev/null; then
    echo "realpath is required but was not found." >&2
    exit 1
fi

INPUT_FILE="$(realpath "$1" 2>/dev/null || true)"
if [ -z "$INPUT_FILE" ] || [ ! -f "$INPUT_FILE" ]; then
    echo "Micron MERC input file not found: $1" >&2
    exit 2
fi

MERC="$SCRIPT_DIR/analyzers/contoso/memory_shims/vendor_tools/micron/merc3_1_1/merc3"
if [ ! -x "$MERC" ]; then
    echo "Micron MERC executable is missing or not executable: $MERC" >&2
    exit 1
fi

MICRON_MOCKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ras-gen1-micron.XXXXXX")"
cleanup_staging() {
    rm -rf -- "$MICRON_MOCKUP_DIR"
}
trap cleanup_staging EXIT

cp -a "$PROJECT_DIR/mockups/ras_gen1/." "$MICRON_MOCKUP_DIR/"
python3 "$SCRIPT_DIR/prepare_micron_demo.py" \
    --template "$MICRON_TEMPLATE" \
    --input-file "$INPUT_FILE" \
    --output "$MICRON_MOCKUP_DIR/ras_endpoint_config.json" || exit 1

wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="$3"
    python3 - "$host" "$port" "$timeout" <<'PY'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
deadline = time.monotonic() + float(sys.argv[3])
while time.monotonic() < deadline:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            raise SystemExit(0)
    except OSError:
        time.sleep(0.25)
raise SystemExit(1)
PY
}

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Killing existing session: $SESSION_NAME"
    tmux kill-session -t "$SESSION_NAME"
fi

printf -v PROJECT_Q '%q' "$PROJECT_DIR"
printf -v SCRIPT_Q '%q' "$SCRIPT_DIR"
printf -v INPUT_Q '%q' "$INPUT_FILE"
printf -v MOCKUP_Q '%q' "$MICRON_MOCKUP_DIR"
printf -v CONFIG_Q '%q' "$MICRON_MOCKUP_DIR/ras_endpoint_config.json"

echo "Starting Micron RAS demo in tmux session: $SESSION_NAME"
echo "MERC input: $INPUT_FILE"

cd "$PROJECT_DIR" || exit 1
tmux new-session -d -s "$SESSION_NAME" -n "RAS-Demo-Micron"
tmux set-option -g mouse on
tmux split-window -h -t "$SESSION_NAME:0.0"
tmux split-window -v -t "$SESSION_NAME:0.0"
tmux set-option -g pane-border-status top
tmux set-option -g pane-border-format " #{pane_title} "
tmux select-pane -t "$SESSION_NAME:0.0" -T "BMC Redfish Server - Micron DIMMs"
tmux select-pane -t "$SESSION_NAME:0.1" -T "SDK Event Listener"
tmux select-pane -t "$SESSION_NAME:0.2" -T "Micron MERC RAS Demo"

tmux send-keys -t "$SESSION_NAME:0.0" "cd $PROJECT_Q" C-m
tmux send-keys -t "$SESSION_NAME:0.0" \
    "trap 'rm -rf -- $MOCKUP_Q' EXIT; python3 -B servers/redfishMockupServer_platform.py -D $MOCKUP_Q -p 8000 --endpoint-config $CONFIG_Q" C-m

tmux send-keys -t "$SESSION_NAME:0.1" "cd $PROJECT_Q" C-m
tmux send-keys -t "$SESSION_NAME:0.1" \
    "python3 examples/ras_api_demo/event_listener_sdk.py --port 8888 --bmc localhost:8000" C-m

tmux send-keys -t "$SESSION_NAME:0.2" "cd $PROJECT_Q" C-m
tmux send-keys -t "$SESSION_NAME:0.2" \
    "echo 'Micron MERC input: $INPUT_Q'" C-m

if wait_for_port localhost 8889 15; then
    tmux send-keys -t "$SESSION_NAME:0.2" \
        "python3 examples/ras_api_demo/reset_server.py --clean-temp && python3 examples/ras_api_demo/init_error_pipeline.py && MICRON_MERC_INPUT_FILE=$INPUT_Q python3 examples/ras_api_demo/ras_api_plugin_demo_micron.py --input-file $INPUT_Q --endpoint-config $CONFIG_Q; tmux send-keys -t $SESSION_NAME:0.2 '$SCRIPT_Q/cleanup_ras_demo.sh'" C-m
else
    tmux send-keys -t "$SESSION_NAME:0.2" \
        "echo 'Event listener control port 8889 did not become ready within 15 seconds.'" C-m
fi

trap - EXIT
tmux select-pane -t "$SESSION_NAME:0.2"

echo ""
echo "Micron demo session created."
echo "Each unique msn/mpn pair in the input is mapped to one Micron DIMM."
echo "Use Ctrl+B then arrow keys to change panes, or Ctrl+B then d to detach."
echo "Run $SCRIPT_DIR/cleanup_ras_demo.sh to stop the demo."
sleep 2
tmux attach-session -t "$SESSION_NAME"
