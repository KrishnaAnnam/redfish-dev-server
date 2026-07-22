#!/usr/bin/env python3
"""
SDK-based Redfish Event Listener with CPER Auto-Download
========================================================

Replaces the raw HTTP event_listener.py with the SDK's RedfishEventListener.
Subscribes to the BMC server, receives push events, and auto-downloads
CPER binaries via AdditionalDataURI.

Usage:
    python Demos/RasApi/event_listener_sdk.py [--port 8888] [--bmc localhost:8000]
"""

import argparse
import asyncio
import base64
import json
import queue
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
    """Display inline CPER extraction result."""
    platform_id, partition_id, _ = parse_cper_header_ids(cper_bytes)
    print(f"\n   📥 CPER EXTRACTED (inline DiagnosticData)")
    print(f"      Size:        {len(cper_bytes)} bytes")
    print(f"      Platform:    {platform_id}")
    print(f"      Partition:   {partition_id}")
    if cper_event.origin_of_condition:
        print(f"      LogEntry:    {cper_event.origin_of_condition}")
    print(f"      Saved:       {save_path}")


# ---------------------------------------------------------------------------
# Notification server — notifies demo client over TCP when CPERs arrive
# ---------------------------------------------------------------------------

class NotificationServer:
    """Bidirectional TCP link with the orchestrator.

    Outbound: pushes JSON notifications (e.g. ``cper_downloaded``) to connected
    clients.  Inbound: reads newline-delimited JSON commands (e.g. ``subscribe``)
    from clients and puts them on ``commands`` for the main loop to act on.
    """

    def __init__(self, port: int = 8889, commands: "queue.Queue | None" = None):
        self.port = port
        self.commands = commands
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
                print(f"   📡 Orchestrator connected from {addr}")
                threading.Thread(
                    target=self._read_loop, args=(conn,), daemon=True).start()
            except OSError:
                break

    def _read_loop(self, conn: socket.socket) -> None:
        """Read newline-delimited JSON commands from one client."""
        buffer = ""
        while True:
            try:
                chunk = conn.recv(4096).decode()
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line or self.commands is None:
                    continue
                try:
                    self.commands.put(json.loads(line))
                except json.JSONDecodeError:
                    pass

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
    parser.add_argument("--bmc", default="localhost:8000", help="Unused; kept for launch-script compatibility. The BMC to subscribe to is provided per 'subscribe' command by the orchestrator.")
    parser.add_argument("--storage", default=None, help="CPER storage directory")
    parser.add_argument("--notify-port", type=int, default=8889, help="Notification port for demo client (default: 8889)")
    args = parser.parse_args()

    storage_dir = Path(args.storage) if args.storage else Path(__file__).resolve().parent / "ras_demo_output" / "cper_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # --- 0. Start the control/notification server for the orchestrator ---
    # Inbound 'subscribe' commands arrive on this queue; outbound
    # 'cper_downloaded' notifications are pushed back over the same socket.
    command_queue: "queue.Queue" = queue.Queue()
    notifier = NotificationServer(port=args.notify_port, commands=command_queue)
    notifier.start()
    print(f"   📡 Control/notification server on port {args.notify_port}")

    # --- 1. Create SDK listener ---
    listener = RedfishEventListener(port=args.port)

    # --- 2. Announce; do NOT subscribe yet ---
    print(f"\n{'=' * 60}")
    print(f"🎧 SDK EVENT LISTENER")
    print(f"{'=' * 60}")
    print(f"   Mode:     Command-driven — waits for the orchestrator to discover")
    print(f"             a host and tell this listener which host(s) to subscribe to")
    print(f"   Registry: OCPRAS (filters: CorrectedError, FatalError, etc.)")
    print(f"   Pattern:  Inline CPER extraction from DiagnosticData")
    print(f"   Flow:     orchestrator subscribe → BMC push → extract CPER → notify")

    # One BMC connection per subscribed host (populated by 'subscribe' commands).
    contexts: list = []

    # --- 3. Register event callback ---
    download_count = 0
    last_notify_time = 0.0

    async def on_event(event: RedfishEvent) -> None:
        nonlocal download_count, last_notify_time
        print_event(event)

        # Auto-download CPER if this is a CPER event
        ce = CperEvent.from_event_record(event.raw)
        mid_lower = ce.message_id.lower()
        if ce.severity is None and "ocpras" not in mid_lower and "cper" not in mid_lower and "ras" not in mid_lower:
            return

        # Inline data needs no host; otherwise try each subscribed host until
        # one serves the CPER binary.  Remember which host it came from so we
        # can delete the LogEntry there.
        cper_bytes = None
        source_ctx = contexts[0] if contexts else None
        if ce.cper_data:
            cper_bytes = ce.cper_data
        else:
            uri = ce.additional_data_uri or (
                ce.origin_of_condition + "/Attachment"
                if ce.origin_of_condition else None)
            if uri:
                for ctx in contexts:
                    try:
                        cper_bytes = await ctx.ras_service.fetch_cper_data_async(uri)
                    except Exception:
                        cper_bytes = None
                    if cper_bytes:
                        source_ctx = ctx
                        break
        if not cper_bytes:
            print("      ❌ Could not download CPER from any subscribed host")

        if cper_bytes:
            download_count += 1
            # Extract IDs from CPER header and organize storage
            platform_id, partition_id, _ = parse_cper_header_ids(cper_bytes)
            cper_dir = storage_dir / platform_id / partition_id
            cper_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"cper_{ts}.cper"
            save_path = cper_dir / filename
            save_path.write_bytes(cper_bytes)
            print_download(ce, cper_bytes, save_path)

            # Delete the individual LogEntry (per OCP RAS API §4.8)
            if ce.origin_of_condition and source_ctx is not None:
                try:
                    del_resp = await source_ctx.delete_async(ce.origin_of_condition)
                    if del_resp.success:
                        print(f"      🗑️  Deleted entry: {ce.origin_of_condition.split('/')[-1]}")
                    else:
                        print(f"      ⚠️  Delete returned {del_resp.status_code}")
                except Exception as e:
                    print(f"      ⚠️  Could not delete entry: {e}")

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
                "severity": ce.severity.value if ce.severity else None,
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
    print(f"   📁 CPER storage: {storage_dir}")
    print(f"   📡 Demo client notification port: {args.notify_port}")

    print(f"\n   Waiting for the orchestrator to send subscribe command(s)...")
    print(f"   (Ctrl+C to stop)")
    print(f"{'=' * 60}\n")

    # --- 5. Subscribe on command from the orchestrator ---
    # Each 'subscribe' command connects to one host and subscribes this listener
    # to its CPER events.  Track them so we can clean up on shutdown.
    subscriptions = []  # list of (bmc, subscription_uri, ctx)

    def handle_subscribe(cmd: dict) -> None:
        bmc = cmd.get("bmc", "")
        host, _, port = bmc.partition(":")
        prefixes = cmd.get("registry_prefixes") or ["OCPRAS"]
        print(f"\n   📥 Subscribe command received for {bmc}")
        try:
            ctx = connect(
                host=host,
                port=int(port or 80),
                credentials=Credentials(
                    username=cmd.get("username") or "admin",
                    password=cmd.get("password") or "admin"),
                auth_mode=AuthMode.STATELESS,
                config=ConnectionConfig(use_tls=False),
            )
        except Exception as e:
            print(f"   ❌ Could not connect to {bmc}: {e}")
            notifier.notify({"event": "subscribed", "bmc": bmc, "subscription_uri": None})
            return

        listener.use_context(ctx)   # for registry resolution
        contexts.append(ctx)

        resp = ctx.ras_service.subscribe_cper_events(
            destination=listen_url,
            registry_prefixes=prefixes,
            resource_types=["LogEntry"],
        )
        subscription_uri = None
        if resp.success:
            body = resp.body if isinstance(resp.body, dict) else {}
            raw = resp.raw if isinstance(resp.raw, dict) else {}
            sub_location = body.get("@odata.id") or raw.get("@odata.id") or body.get("Id")
            if sub_location and not str(sub_location).startswith("/"):
                sub_location = f"/redfish/v1/EventService/Subscriptions/{sub_location}"
            subscription_uri = sub_location
            subscriptions.append((bmc, subscription_uri, ctx))
            print(f"   ✅ Subscribed to {bmc}")
            print(f"      RegistryPrefixes: {prefixes}")
            print(f"      Destination:      {listen_url}")
            if subscription_uri:
                print(f"      URI:              {subscription_uri}")
        else:
            print(f"   ⚠️  Subscription failed: {resp.status_code}")
        notifier.notify({
            "event": "subscribed", "bmc": bmc, "subscription_uri": subscription_uri})

    def handle_unsubscribe(cmd: dict) -> None:
        bmc = cmd.get("bmc", "")
        sub_uri = cmd.get("subscription_uri")
        print(f"\n   📥 Unsubscribe command received for {bmc}")
        removed = False
        for entry in list(subscriptions):
            entry_bmc, entry_uri, ctx = entry
            if entry_bmc != bmc or (sub_uri and entry_uri != sub_uri):
                continue
            if entry_uri:
                try:
                    del_resp = ctx.delete(entry_uri)
                    if del_resp.success:
                        print(f"   🗑️  Subscription removed on {bmc}: {entry_uri}")
                    else:
                        print(f"   ⚠️  Could not remove subscription on {bmc}: {del_resp.status_code}")
                except Exception as e:
                    print(f"   ⚠️  Subscription cleanup failed on {bmc}: {e}")
            subscriptions.remove(entry)
            if ctx in contexts:
                contexts.remove(ctx)
            try:
                ctx.close()
            except Exception:
                pass
            removed = True
        notifier.notify({"event": "unsubscribed", "bmc": bmc, "removed": removed})

    def handle_store_cper(cmd: dict) -> None:
        """Store an externally-supplied CPER as if it arrived from the host.

        Used for operator-generated CPERs (e.g. a policy-rejection Platform
        Action CPER): the bytes are written under the same cper_storage tree as
        downloaded CPERs and the orchestrator is notified the same way.
        """
        try:
            cper_bytes = base64.b64decode(cmd.get("cper_b64", ""))
        except Exception as e:
            print(f"   ⚠️  store_cper: invalid base64 ({e})")
            return
        if not cper_bytes:
            print("   ⚠️  store_cper: empty CPER")
            return
        platform_id, partition_id, _ = parse_cper_header_ids(cper_bytes)
        cper_dir = storage_dir / platform_id / partition_id
        cper_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"cper_{ts}.cper"
        save_path = cper_dir / filename
        save_path.write_bytes(cper_bytes)
        print(f"\n   📥 Stored externally-supplied CPER: {save_path}")
        notifier.notify({
            "event": "cper_downloaded",
            "file": filename,
            "path": str(save_path),
            "platform_id": platform_id,
            "partition_id": partition_id,
            "size": len(cper_bytes),
            "message_id": cmd.get("message_id", "policy.rejected"),
            "severity": cmd.get("severity"),
        })

    # --- 6. Shutdown handling ---
    def handle_signal(sig, frame):
        print(f"\n\n{'=' * 60}")
        print(f"📊 SESSION SUMMARY")
        print(f"{'=' * 60}")
        events = listener.get_buffered_events()
        print(f"   Events received:    {len(events)}")
        print(f"   CPERs extracted:    {download_count}")
        print(f"   CPER storage:       {storage_dir}")
        for bmc, subscription_uri, ctx in subscriptions:
            if not subscription_uri:
                continue
            try:
                del_resp = ctx.delete(subscription_uri)
                if del_resp.success:
                    print(f"   🗑️  Subscription removed on {bmc}: {subscription_uri}")
                else:
                    print(f"   ⚠️  Could not remove subscription on {bmc}: {del_resp.status_code}")
            except Exception as e:
                print(f"   ⚠️  Subscription cleanup failed on {bmc}: {e}")
        for ctx in contexts:
            try:
                ctx.close()
            except Exception:
                pass
        print(f"{'=' * 60}")
        notifier.stop()
        listener.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # --- 7. Command loop: block on the queue, act on commands ---
    while True:
        try:
            cmd = command_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if cmd.get("command") == "subscribe":
            handle_subscribe(cmd)
        elif cmd.get("command") == "unsubscribe":
            handle_unsubscribe(cmd)
        elif cmd.get("command") == "store_cper":
            handle_store_cper(cmd)
        else:
            print(f"   ⚠️  Ignoring unknown command: {cmd!r}")


if __name__ == "__main__":
    main()
