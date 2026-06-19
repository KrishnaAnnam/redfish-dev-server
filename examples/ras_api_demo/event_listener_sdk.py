#!/usr/bin/env python3
"""
SDK-based Redfish Event Listener with CPER Auto-Download
========================================================

Replaces the raw HTTP event_listener.py with the SDK's RedfishEventListener.
Subscribes to the BMC server, receives push events, and auto-downloads
CPER binaries via AdditionalDataURI.

Usage:
    python examples/ras_api_demo/event_listener_sdk.py [--port 8888] [--bmc localhost:8000]
"""

import argparse
import asyncio
import json
import signal
import socket
import struct
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from redfish_sdk import (
    connect,
    RedfishEventListener,
    RedfishEvent,
    Credentials,
    AuthMode,
    ConnectionConfig,
    CperEvent,
)


# ---------------------------------------------------------------------------
# CPER header parsing
# ---------------------------------------------------------------------------

def _parse_cper_guid(data: bytes, offset: int) -> str:
    """Parse a mixed-endian GUID from CPER binary at the given offset.

    CPER GUIDs are stored as: Data1(4B LE) Data2(2B LE) Data3(2B LE) Data4(8B BE).
    Returns a lowercase UUID string like '990f8820-bd4d-5064-58cc-961a053dea79'.
    """
    if len(data) < offset + 16:
        return "unknown"
    d1, d2, d3 = struct.unpack_from("<IHH", data, offset)
    d4 = data[offset + 8 : offset + 16]
    return str(uuid.UUID(fields=(d1, d2, d3, d4[0], d4[1], int.from_bytes(d4[2:], "big"))))


def parse_cper_header_ids(cper_bytes: bytes) -> tuple[str, str, str]:
    """Extract (platform_id, partition_id, creator_id) from CPER header.

    Offsets per UEFI CPER spec:
      Platform ID:   offset 32, 16 bytes
      Partition ID:  offset 48, 16 bytes
      Creator ID:    offset 64, 16 bytes
    """
    platform_id = _parse_cper_guid(cper_bytes, 32)
    partition_id = _parse_cper_guid(cper_bytes, 48)
    creator_id = _parse_cper_guid(cper_bytes, 64)
    return platform_id, partition_id, creator_id


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_event(event: RedfishEvent) -> None:
    """Display a received event."""
    print(f"\n{'=' * 60}")
    print(f"🔔 EVENT RECEIVED  ⏰ {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'=' * 60}")
    print(f"   Message ID:  {event.message_id}")
    print(f"   Severity:    {event.severity or 'N/A'}")
    print(f"   Message:     {event.message}")
    if event.origin_of_condition:
        print(f"   Origin:      {event.origin_of_condition}")
    if event.raw.get("AdditionalDataURI"):
        print(f"   DataURI:     {event.raw['AdditionalDataURI']}")


def print_download(cper_event: CperEvent, cper_bytes: bytes, save_path: Path) -> None:
    """Display auto-download result."""
    platform_id, partition_id, _ = parse_cper_header_ids(cper_bytes)
    print(f"\n   📥 CPER AUTO-DOWNLOADED")
    print(f"      Size:        {len(cper_bytes)} bytes")
    print(f"      Platform:    {platform_id}")
    print(f"      Partition:   {partition_id}")
    if cper_event.origin_of_condition:
        print(f"      Source:      {cper_event.origin_of_condition}")
    print(f"      Saved:       {save_path}")


# ---------------------------------------------------------------------------
# Notification server — notifies demo client over TCP when CPERs arrive
# ---------------------------------------------------------------------------

class NotificationServer:
    """Simple TCP server that pushes JSON notifications to connected clients."""

    def __init__(self, port: int = 8889):
        self.port = port
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._server: socket.socket | None = None

    def start(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", self.port))
        self._server.listen(4)
        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()

    def _accept_loop(self) -> None:
        while True:
            try:
                conn, addr = self._server.accept()
                with self._lock:
                    self._clients.append(conn)
                print(f"   📡 Demo client connected from {addr}")
            except OSError:
                break

    def notify(self, payload: dict) -> None:
        """Send a JSON notification (newline-delimited) to all connected clients."""
        data = (json.dumps(payload) + "\n").encode()
        with self._lock:
            alive = []
            for c in self._clients:
                try:
                    c.sendall(data)
                    alive.append(c)
                except OSError:
                    pass
            self._clients = alive

    def stop(self) -> None:
        if self._server:
            self._server.close()
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="SDK-based Redfish Event Listener")
    parser.add_argument("--port", type=int, default=8888, help="Listener port (default: 8888)")
    parser.add_argument("--bmc", default="localhost:8000", help="BMC host:port (default: localhost:8000)")
    parser.add_argument("--storage", default=None, help="CPER storage directory")
    parser.add_argument("--notify-port", type=int, default=8889, help="Notification port for demo client (default: 8889)")
    args = parser.parse_args()

    bmc_host, bmc_port = args.bmc.split(":")
    bmc_port = int(bmc_port)
    storage_dir = Path(args.storage) if args.storage else Path(__file__).resolve().parent / "ras_demo_output" / "cper_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # --- 0. Start notification server for demo client ---
    notifier = NotificationServer(port=args.notify_port)
    notifier.start()
    print(f"   📡 Notification server on port {args.notify_port}")

    # --- 1. Create SDK listener ---
    listener = RedfishEventListener(port=args.port)

    # --- 2. Connect to BMC ---
    print(f"\n{'=' * 60}")
    print(f"🎧 SDK EVENT LISTENER")
    print(f"{'=' * 60}")
    print(f"   Connecting to BMC at {bmc_host}:{bmc_port}...")

    ctx = connect(
        host=bmc_host,
        port=bmc_port,
        credentials=Credentials(username="admin", password="admin"),
        auth_mode=AuthMode.STATELESS,
        config=ConnectionConfig(use_tls=False),
    )
    print(f"   ✅ Connected to BMC")

    # Attach context to listener for registry resolution
    listener.use_context(ctx)

    # --- 3. Register event callback ---
    download_count = 0
    last_notify_time = 0.0

    async def on_event(event: RedfishEvent) -> None:
        nonlocal download_count, last_notify_time
        print_event(event)

        # Auto-download CPER if this is a CPER event
        ce = CperEvent.from_event_record(event.raw)
        mid_lower = ce.message_id.lower()
        if ce.severity is None and "cper" not in mid_lower and "ras" not in mid_lower:
            return

        cper_bytes = None
        if ce.additional_data_uri:
            try:
                cper_bytes = await ctx.ras_service.fetch_cper_data_async(ce.additional_data_uri)
            except Exception as e:
                print(f"      ❌ Download failed: {e}")
        elif ce.cper_data:
            cper_bytes = ce.cper_data
        elif ce.origin_of_condition:
            try:
                resp = await ctx.get_async(ce.origin_of_condition + "/Attachment")
                if resp.success:
                    cper_bytes = (resp.raw or "").encode()
            except Exception as e:
                print(f"      ❌ Attachment fetch failed: {e}")

        if cper_bytes:
            download_count += 1
            # Extract IDs from CPER header and organize storage
            platform_id, partition_id, _ = parse_cper_header_ids(cper_bytes)
            cper_dir = storage_dir / platform_id / partition_id
            cper_dir.mkdir(parents=True, exist_ok=True)
            filename = f"cper_{download_count:04d}.cper"
            save_path = cper_dir / filename
            save_path.write_bytes(cper_bytes)
            print_download(ce, cper_bytes, save_path)

            # Clear the RAS LogService so entries don't accumulate
            try:
                log_uri = f"/redfish/v1/Managers/System/LogServices/RAS"
                clear_resp = await ctx.log_service.clear_log_async(log_uri)
                if clear_resp.success:
                    print(f"      🗑️  Server log cleared")
                else:
                    print(f"      ⚠️  Log clear returned {clear_resp.status_code}")
            except Exception as e:
                print(f"      ⚠️  Could not clear server log: {e}")

            # Notify the demo client that a CPER was downloaded
            import time as _time
            now = _time.time()
            should_notify = (now - last_notify_time) > 3
            notifier.notify({
                "event": "cper_downloaded",
                "file": filename,
                "path": str(save_path),
                "platform_id": platform_id,
                "partition_id": partition_id,
                "size": len(cper_bytes),
                "message_id": ce.message_id,
                "severity": ce.severity,
            })
            if should_notify:
                last_notify_time = now
                await asyncio.sleep(2)
                print(f"\n      📡 Sending notification to demo client...")
                print(f"      ✅ Demo client notified")

    listener.on_event(on_event)

    # --- 4. Start listener ---
    listener.start()
    listen_url = listener.listen_url.replace("0.0.0.0", "localhost")
    print(f"   ✅ Listening on {listen_url}")
    print(f"   📁 Storage: {storage_dir}")

    # --- 5. Subscribe to BMC events ---
    print(f"\n   Subscribing to BMC events...")

    # Check if we already have a subscription pointing to our listener
    already_subscribed = False
    try:
        import requests as req
        subs_url = f"http://{args.bmc}/redfish/v1/EventService/Subscriptions"
        subs_resp = req.get(subs_url, timeout=5)
        if subs_resp.status_code == 200:
            members = subs_resp.json().get("Members", [])
            for member in members:
                sub_uri = member.get("@odata.id", "")
                sub_resp = req.get(f"http://{args.bmc}{sub_uri}", timeout=5)
                if sub_resp.status_code == 200:
                    sub_data = sub_resp.json()
                    if sub_data.get("Destination") == listen_url:
                        already_subscribed = True
                        print(f"   ✅ Reusing existing subscription: {sub_uri}")
                        break
    except Exception:
        pass

    if not already_subscribed:
        resp = ctx.ras_service.subscribe_cper_events(
            destination=listen_url,
            registry_prefixes=["OemCper"],
        )
        if resp.success:
            print(f"   ✅ Subscribed for CPER events")
        else:
            print(f"   ⚠️  Subscription response: {resp.status_code}")

    print(f"\n   Waiting for events... (Ctrl+C to stop)")
    print(f"{'=' * 60}\n")

    # --- 6. Block until Ctrl+C ---
    shutdown = False

    def handle_signal(sig, frame):
        nonlocal shutdown
        if not shutdown:
            shutdown = True
            print(f"\n\n{'=' * 60}")
            print(f"📊 SESSION SUMMARY")
            print(f"{'=' * 60}")
            events = listener.get_buffered_events()
            print(f"   Events received:  {len(events)}")
            print(f"   CPERs downloaded: {download_count}")
            print(f"   Storage:          {storage_dir}")
            print(f"{'=' * 60}")
            notifier.stop()
            listener.stop()
            ctx.close()
            sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    signal.pause()


if __name__ == "__main__":
    main()
