from __future__ import annotations

import threading
import time
import socket
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Full, Queue
import sys
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Protocole.CAN.Drivers.pcSim.pc_sim_client import PcSimClient

from .config import CanClientConfig, EcuConfig, MonitorConfig


@dataclass
class _CanFilter:
    node: Optional[int] = None
    can_id: Optional[int] = None
    mask: int = 0x1FFFFFFF
    extended: Optional[bool] = None


@dataclass
class _BrokerPeer:
    name: str
    client: PcSimClient
    nodes: Optional[set]
    filters: List[_CanFilter]
    dynamic_filters: List[_CanFilter] = field(default_factory=list)
    last_rx_refresh_s: float = 0.0


class PcSimCanBrokerService:
    def __init__(self, cfg: MonitorConfig) -> None:
        self._cfg = cfg
        self._control_port = int(cfg.can_broker_control_port)
        self._poll_sleep_s = max(0.0, float(cfg.can_broker_poll_sleep_s))
        self._max_pop = max(1, int(cfg.can_broker_max_pop_per_ecu))
        self._max_inject = max(1, int(cfg.can_broker_max_inject_per_cycle))
        self._log_all = bool(cfg.can_broker_log_all)
        self._log_rules = {
            str(peer_name).strip().upper(): {str(direction).strip().lower() for direction in directions if str(direction).strip()}
            for peer_name, directions in cfg.can_broker_log_rules.items()
            if str(peer_name).strip()
        }
        self._rx_refresh_period_s = 1.0
        self._peers: List[_BrokerPeer] = self._build_peers(cfg.ecus, cfg.can_clients)
        self._peer_order: List[str] = [peer.name for peer in self._peers]
        self._rr_index = 0
        self._max_batch_per_cycle = max(32, len(self._peers) * 8)
        queue_depth_per_peer = max(256, self._max_inject * 4)
        self._rx_queues: Dict[str, Queue[Dict[str, Any]]] = {
            peer.name: Queue(maxsize=queue_depth_per_peer) for peer in self._peers
        }

        self._stop_evt = threading.Event()
        self._rx_ready_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rx_threads: List[threading.Thread] = []
        self._control_sock: Optional[socket.socket] = None
        self._is_owner = False
        self._external_detected = False
        self._stats_lock = threading.Lock()
        self._error_log_lock = threading.Lock()
        self._error_log_state: Dict[str, Tuple[str, float]] = {}
        self._stats: Dict[str, int] = {
            "rx_frames": 0,
            "routed_frames": 0,
            "injected_frames": 0,
            "dropped_frames": 0,
            "cycle_errors": 0,
            "last_cycle_ms": 0,
        }

    def _should_log_for_peers(self, *peer_names: str) -> bool:
        if self._log_all:
            return True
        if not self._log_rules:
            return False
        for peer_name in peer_names:
            if str(peer_name).strip().upper() in self._log_rules:
                return True
        return False

    def _should_log_route(self, src_name: str, routed_peers: List[str], skipped_peers: List[str], failed_peers: List[str]) -> bool:
        if self._log_all:
            return True
        if not self._log_rules:
            return False
        src_directions = self._log_rules.get(str(src_name).strip().upper(), set())
        if "tx" in src_directions:
            return True
        dst_names = []
        dst_names.extend(routed_peers)
        dst_names.extend(item.split(" (", 1)[0] for item in skipped_peers)
        dst_names.extend(item.split(" (", 1)[0] for item in failed_peers)
        for dst_name in dst_names:
            dst_directions = self._log_rules.get(str(dst_name).strip().upper(), set())
            if "rx" in dst_directions:
                return True
        return False

    def _should_log_pair(self, src_name: str, dst_name: str) -> bool:
        if self._log_all:
            return True
        if not self._log_rules:
            return False
        src_directions = self._log_rules.get(str(src_name).strip().upper(), set())
        dst_directions = self._log_rules.get(str(dst_name).strip().upper(), set())
        return ("tx" in src_directions) or ("rx" in dst_directions)

    def _log_error(self, context: str, exc: Exception, *peer_names: str) -> None:
        if not self._should_log_for_peers(*peer_names):
            return
        now_s = time.monotonic()
        message = f"{exc.__class__.__name__}: {exc}"
        with self._error_log_lock:
            prev = self._error_log_state.get(context)
            should_print = prev is None or prev[0] != message or (now_s - prev[1]) >= 1.0
            self._error_log_state[context] = (message, now_s)
        if should_print:
            print(f"[ERROR] CAN broker {context}: {message}")

    def _clear_error(self, context: str) -> None:
        with self._error_log_lock:
            self._error_log_state.pop(context, None)

    @staticmethod
    def _format_peer_nodes(peer: _BrokerPeer) -> str:
        if not peer.nodes:
            return "ALL"
        return ",".join(str(v) for v in sorted(peer.nodes))

    @staticmethod
    def _format_peer_filters(peer: _BrokerPeer) -> str:
        if peer.filters:
            return f"static:{len(peer.filters)}"
        return "dynamic-or-none"

    def _log_peer_topology(self) -> None:
        print(f"[INFO] CAN broker peer topology ({len(self._peers)} peer(s)):")
        for peer in self._peers:
            if not self._should_log_for_peers(peer.name):
                continue
            host, port = peer.client.addr
            print(
                "[INFO] "
                f"peer='{peer.name}' "
                f"udp={host}:{port} "
                f"nodes={self._format_peer_nodes(peer)} "
                f"filters={self._format_peer_filters(peer)}"
            )
        if self._log_rules:
            rules_txt = ", ".join(
                f"{peer}:[{','.join(sorted(directions))}]"
                for peer, directions in sorted(self._log_rules.items())
            )
            print(
                "[INFO] CAN broker log filter "
                f"rules={rules_txt}"
            )
        else:
            print(
                "[INFO] CAN broker log filter "
                f"log_all={int(self._log_all)} rules=none"
            )

    @staticmethod
    def _parse_filter(raw: Dict[str, Any]) -> _CanFilter:
        node = raw.get("node")
        can_id = raw.get("id", raw.get("can_id"))
        mask = raw.get("mask", 0x1FFFFFFF)
        ext = raw.get("extended")
        return _CanFilter(
            node=int(node) if node is not None else None,
            can_id=int(can_id, 0) if isinstance(can_id, str) else (int(can_id) if can_id is not None else None),
            mask=int(mask, 0) if isinstance(mask, str) else int(mask),
            extended=bool(ext) if ext is not None else None,
        )

    def _peer_from_endpoint(
        self,
        name: str,
        udp_host: str,
        udp_port: int,
        udp_timeout_s: float,
        nodes_raw: List[int],
        filters_raw: List[Dict[str, Any]],
    ) -> _BrokerPeer:
        nodes = set(int(n) for n in nodes_raw) if nodes_raw else None
        filters = [self._parse_filter(f) for f in filters_raw]
        return _BrokerPeer(
            name=name,
            client=PcSimClient(host=udp_host, port=udp_port, timeout=udp_timeout_s),
            nodes=nodes,
            filters=filters,
        )

    def _build_peers(self, ecus: List[EcuConfig], can_clients: List[CanClientConfig]) -> List[_BrokerPeer]:
        peers: List[_BrokerPeer] = []
        for ecu in ecus:
            if str(ecu.can_gate).upper() != "PCSIM":
                continue
            if (not ecu.enable_ecu) and (not ecu.ecu_in_debug):
                continue
            peers.append(
                self._peer_from_endpoint(
                    name=ecu.name,
                    udp_host=ecu.udp.host,
                    udp_port=ecu.udp.port,
                    udp_timeout_s=ecu.udp.timeout_s,
                    nodes_raw=ecu.pcsim_shared_can_nodes,
                    filters_raw=ecu.pcsim_rx_filters,
                )
            )
        for client in can_clients:
            if not client.enable_client:
                continue
            if str(client.can_gate).upper() != "PCSIM":
                continue
            peers.append(
                self._peer_from_endpoint(
                    name=client.name,
                    udp_host=client.udp.host,
                    udp_port=client.udp.port,
                    udp_timeout_s=client.udp.timeout_s,
                    nodes_raw=client.pcsim_shared_can_nodes,
                    filters_raw=client.pcsim_rx_filters,
                )
            )
        return peers

    @property
    def is_enabled(self) -> bool:
        return self._cfg.can_broker_enabled and len(self._peers) > 1

    @property
    def is_owner(self) -> bool:
        return self._is_owner

    @property
    def external_detected(self) -> bool:
        return self._external_detected

    @property
    def control_port(self) -> int:
        return self._control_port

    @staticmethod
    def ping_control(port: int, timeout_s: float = 0.2) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout_s)
                sock.sendto(b"PING", ("127.0.0.1", int(port)))
                data, _ = sock.recvfrom(256)
                return data.decode("ascii", errors="ignore").strip() == "PONG"
        except Exception:
            return False

    def _try_bind_control(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", self._control_port))
            sock.setblocking(False)
            self._control_sock = sock
            return True
        except Exception:
            self._control_sock = None
            return False

    def _process_control_requests(self) -> None:
        if self._control_sock is None:
            return
        while True:
            try:
                data, addr = self._control_sock.recvfrom(512)
            except BlockingIOError:
                break
            except Exception:
                break
            cmd = data.decode("ascii", errors="ignore").strip().upper()
            if cmd == "PING":
                reply = "PONG"
            elif cmd == "STATS":
                st = self.get_stats()
                reply = (
                    f"OK RX={st['rx_frames']} ROUTED={st['routed_frames']} "
                    f"INJ={st['injected_frames']} DROP={st['dropped_frames']} "
                    f"ERR={st['cycle_errors']}"
                )
            else:
                reply = "ERR"
            try:
                self._control_sock.sendto(reply.encode("ascii"), addr)
            except Exception:
                pass

    def start(self) -> None:
        if not self.is_enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._external_detected = False
        self._is_owner = False
        if not self._try_bind_control():
            self._external_detected = self.ping_control(self._control_port)
            if self._external_detected:
                print(f"[INFO] CAN broker already running on control port {self._control_port}")
            else:
                print(f"[WARNING] CAN broker control port {self._control_port} busy (unknown owner)")
            return
        self._is_owner = True
        self._log_peer_topology()
        for peer in self._peers:
            try:
                peer.client.clear_can_broker_tx()
            except Exception:
                pass
        for rx_queue in self._rx_queues.values():
            while True:
                try:
                    rx_queue.get_nowait()
                except Empty:
                    break
        self._rx_ready_evt.clear()
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, name="pcsim-can-broker", daemon=True)
        self._thread.start()
        self._rx_threads = []
        for peer in self._peers:
            t = threading.Thread(
                target=self._peer_rx_loop,
                args=(peer,),
                name=f"pcsim-can-broker-rx-{peer.name}",
                daemon=True,
            )
            t.start()
            self._rx_threads.append(t)

    def stop(self) -> None:
        self._stop_evt.set()
        for t in self._rx_threads:
            t.join(timeout=1.0)
        self._rx_threads = []
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._control_sock is not None:
            try:
                self._control_sock.close()
            except Exception:
                pass
            self._control_sock = None
        self._is_owner = False

    def get_stats(self) -> Dict[str, int]:
        with self._stats_lock:
            return dict(self._stats)

    def _add_stats(self, **kwargs: int) -> None:
        with self._stats_lock:
            for key, delta in kwargs.items():
                if key in self._stats:
                    self._stats[key] += int(delta)

    @staticmethod
    def _frame_matches_filter(frame: Dict[str, Any], flt: _CanFilter) -> bool:
        node = int(frame.get("node", 0))
        can_id = int(frame.get("can_id", 0))
        is_ext = bool(frame.get("is_extended", True))

        if flt.node is not None and node != flt.node:
            return False
        if flt.extended is not None and is_ext != flt.extended:
            return False
        if flt.can_id is None:
            return True
        return (can_id & flt.mask) == (flt.can_id & flt.mask)

    def _peer_accepts(self, peer: _BrokerPeer, frame: Dict[str, Any]) -> Tuple[bool, str]:
        node = int(frame.get("node", 0))
        if peer.nodes is not None and node not in peer.nodes:
            return False, f"node {node} not in [{self._format_peer_nodes(peer)}]"
        active_filters = peer.filters if peer.filters else peer.dynamic_filters
        if not active_filters:
            return True, "accepted"
        for flt in active_filters:
            if self._frame_matches_filter(frame, flt):
                return True, "accepted"
        return False, "no rx filter match"

    @staticmethod
    def _format_frame(frame: Dict[str, Any]) -> str:
        node = int(frame.get("node", 0))
        can_id = int(frame.get("can_id", 0))
        is_ext = bool(frame.get("is_extended", True))
        dlc = int(frame.get("dlc", len(list(frame.get("data", [])))))
        return f"node={node} id=0x{can_id:X} ext={int(is_ext)} dlc={dlc}"

    @staticmethod
    def _format_route_list(items: List[str]) -> str:
        if not items:
            return "-"
        return ", ".join(items)

    @staticmethod
    def _format_filter(flt: _CanFilter) -> str:
        node = "*" if flt.node is None else str(flt.node)
        can_id = "*" if flt.can_id is None else f"0x{int(flt.can_id):X}"
        ext = "*" if flt.extended is None else str(int(bool(flt.extended)))
        return f"node={node}/id={can_id}/mask=0x{int(flt.mask):X}/ext={ext}"

    def _format_filters_summary(self, filters: List[_CanFilter], max_items: int = 6) -> str:
        if not filters:
            return "none"
        items = [self._format_filter(flt) for flt in filters[:max_items]]
        if len(filters) > max_items:
            items.append(f"...+{len(filters) - max_items}")
        return "; ".join(items)

    def _should_log_tx_for_peer(self, peer_name: str) -> bool:
        if self._log_all:
            return True
        if not self._log_rules:
            return False
        return "tx" in self._log_rules.get(str(peer_name).strip().upper(), set())

    def _should_log_rx_for_peer(self, peer_name: str) -> bool:
        if self._log_all:
            return True
        if not self._log_rules:
            return False
        return "rx" in self._log_rules.get(str(peer_name).strip().upper(), set())

    @staticmethod
    def _filters_from_runtime_regs(regs: List[Dict[str, Any]]) -> List[_CanFilter]:
        out: List[_CanFilter] = []
        for reg in regs:
            try:
                out.append(
                    _CanFilter(
                        node=int(reg.get("node", 0)),
                        can_id=int(reg.get("can_id", 0)),
                        mask=int(reg.get("mask", 0x1FFFFFFF)),
                        extended=bool(reg.get("is_extended", True)),
                    )
                )
            except Exception:
                continue
        return out

    def _peer_rx_loop(self, src: _BrokerPeer) -> None:
        while not self._stop_evt.is_set():
            try:
                now_s = time.monotonic()
                if (now_s - src.last_rx_refresh_s) >= self._rx_refresh_period_s:
                    try:
                        src.dynamic_filters = self._filters_from_runtime_regs(
                            src.client.dump_can_rx_reg_burst(64)
                        )
                        src.last_rx_refresh_s = now_s
                        self._clear_error(f"rx filters peer '{src.name}'")
                    except Exception as exc:
                        self._log_error(f"rx filters peer '{src.name}'", exc, src.name)

                frames = src.client.pop_can_broker_tx_burst(self._max_pop)
                self._clear_error(f"rx loop peer '{src.name}'")
                if not frames:
                    continue
                if self._should_log_tx_for_peer(src.name):
                    print(
                        "[BROKER] "
                        f"peer {src.name} popped {len(frames)} broker tx frame(s): "
                        f"{'; '.join(self._format_frame(frame) for frame in frames[:6])}"
                    )
                self._add_stats(rx_frames=len(frames))
                src_queue = self._rx_queues[src.name]
                for frame in frames:
                    try:
                        src_queue.put_nowait(frame)
                        self._rx_ready_evt.set()
                    except Full:
                        self._add_stats(dropped_frames=1)
                        break
            except Exception as exc:
                self._add_stats(cycle_errors=1)
                self._log_error(f"rx loop peer '{src.name}'", exc, src.name)
                if self._poll_sleep_s > 0.0:
                    time.sleep(self._poll_sleep_s)

    def _get_next_frame(self, timeout_s: float) -> Optional[Tuple[str, Dict[str, Any]]]:
        if not self._peer_order:
            return None
        deadline_s = time.monotonic() + max(0.0, timeout_s)
        while not self._stop_evt.is_set():
            remaining_s = max(0.0, deadline_s - time.monotonic())
            if not self._rx_ready_evt.wait(timeout=remaining_s):
                return None

            peer_count = len(self._peer_order)
            for offset in range(peer_count):
                idx = (self._rr_index + offset) % peer_count
                peer_name = self._peer_order[idx]
                peer_queue = self._rx_queues[peer_name]
                try:
                    frame = peer_queue.get_nowait()
                    self._rr_index = (idx + 1) % peer_count
                    return peer_name, frame
                except Empty:
                    continue

            self._rx_ready_evt.clear()
            if time.monotonic() >= deadline_s:
                return None
        return None

    def _process_frame(self, src_name: str, frame: Dict[str, Any]) -> Tuple[int, int, int]:
        routed = 0
        injected = 0
        dropped = 0
        per_dst_count: Dict[str, int] = {}
        routed_peers: List[str] = []
        skipped_peers: List[str] = []
        failed_peers: List[str] = []

        for dst in self._peers:
            if dst.name == src_name:
                continue
            accepted, reason = self._peer_accepts(dst, frame)
            if self._should_log_pair(src_name, dst.name):
                print(
                    "[BROKER] "
                    f"route check {src_name} -> {dst.name} "
                    f"{self._format_frame(frame)} "
                    f"accepted={accepted} reason={reason}"
                )
            if not accepted:
                skipped_peers.append(f"{dst.name} ({reason})")
                continue
            cnt = per_dst_count.get(dst.name, 0)
            if cnt >= self._max_inject:
                skipped_peers.append(f"{dst.name} (max_inject reached)")
                dropped += 1
                continue
            try:
                rsp = dst.client.inject_can_ex(
                    int(frame.get("node", 0)),
                    int(frame.get("can_id", 0)),
                    bool(frame.get("is_extended", True)),
                    [int(v) & 0xFF for v in list(frame.get("data", []))],
                )
                per_dst_count[dst.name] = cnt + 1
                routed += 1
                injected += 1
                routed_peers.append(dst.name)
                if self._should_log_pair(src_name, dst.name):
                    print(
                        "[BROKER] "
                        f"inject ok {src_name} -> {dst.name} "
                        f"{self._format_frame(frame)} rsp={rsp}"
                    )
                self._clear_error(f"inject '{src_name}' -> '{dst.name}'")
            except Exception as exc:
                failed_peers.append(f"{dst.name} ({exc.__class__.__name__}: {exc})")
                self._log_error(
                    f"inject '{src_name}' -> '{dst.name}'",
                    exc,
                    src_name,
                    dst.name,
                )
                dropped += 1

        if self._should_log_route(src_name, routed_peers, skipped_peers, failed_peers):
            print(
                "[BROKER] "
                f"frame from {src_name} {self._format_frame(frame)} "
                f"routed to: {self._format_route_list(routed_peers)} "
                f"/ skipped: {self._format_route_list(skipped_peers)} "
                f"/ failed: {self._format_route_list(failed_peers)}"
            )
        return routed, injected, dropped

    def _run(self) -> None:
        print(f"[INFO] CAN broker started with {len(self._peers)} PCSIM peer(s) on ctrl {self._control_port}")
        while not self._stop_evt.is_set():
            t0 = time.perf_counter()
            processed = 0
            routed_total = 0
            injected_total = 0
            dropped_total = 0
            try:
                while processed < self._max_batch_per_cycle and not self._stop_evt.is_set():
                    timeout_s = 0.01 if processed == 0 else 0.0
                    item = self._get_next_frame(timeout_s)
                    if item is None:
                        break
                    src_name, frame = item
                    routed, injected, dropped = self._process_frame(src_name, frame)
                    routed_total += routed
                    injected_total += injected
                    dropped_total += dropped
                    processed += 1

                if processed > 0:
                    dt_ms = int((time.perf_counter() - t0) * 1000.0)
                    self._add_stats(
                        routed_frames=routed_total,
                        injected_frames=injected_total,
                        dropped_frames=dropped_total,
                    )
                    with self._stats_lock:
                        self._stats["last_cycle_ms"] = dt_ms
            except Exception as exc:
                self._add_stats(cycle_errors=1)
                self._log_error("main loop", exc)

            self._process_control_requests()
            if processed == 0 and self._poll_sleep_s > 0.0:
                time.sleep(self._poll_sleep_s)

        print("[INFO] CAN broker stopped")
