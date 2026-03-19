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
    origin: str = "endpoint"
    dynamic_filters: List[_CanFilter] = field(default_factory=list)
    last_rx_refresh_s: float = 0.0
    last_error_log_s: float = 0.0
    last_error_msg: str = ""


class PcSimCanBrokerService:
    def __init__(self, cfg: MonitorConfig) -> None:
        self._cfg = cfg
        self._control_port = int(cfg.can_broker_control_port)
        self._poll_sleep_s = max(0.0, float(cfg.can_broker_poll_sleep_s))
        self._max_pop = max(1, int(cfg.can_broker_max_pop_per_ecu))
        self._max_inject = max(1, int(cfg.can_broker_max_inject_per_cycle))
        self._rx_refresh_period_s = 1.0
        self._peers: List[_BrokerPeer] = self._build_peers(cfg.ecus, cfg.can_clients)
        queue_depth = max(256, len(self._peers) * self._max_inject * 8)
        self._rx_queue: Queue[Tuple[str, Dict[str, Any]]] = Queue(maxsize=queue_depth)

        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._rx_threads: List[threading.Thread] = []
        self._control_sock: Optional[socket.socket] = None
        self._is_owner = False
        self._external_detected = False
        self._stats_lock = threading.Lock()
        self._stats: Dict[str, int] = {
            "rx_frames": 0,
            "routed_frames": 0,
            "injected_frames": 0,
            "dropped_frames": 0,
            "cycle_errors": 0,
            "last_cycle_ms": 0,
        }
        self._peer_error_log_period_s = 2.0
        self._route_warn_log_period_s = 2.0
        self._route_info_log_period_s = 0.5
        self._last_route_warn_s: Dict[str, float] = {}
        self._last_route_info_s: Dict[str, float] = {}

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

    @staticmethod
    def _peer_from_endpoint(
        name: str,
        udp_host: str,
        udp_port: int,
        udp_timeout_s: float,
        shared_nodes: List[int],
        rx_filters: List[Dict[str, Any]],
        origin: str,
    ) -> _BrokerPeer:
        nodes = set(int(n) for n in shared_nodes) if shared_nodes else None
        filters = [PcSimCanBrokerService._parse_filter(f) for f in rx_filters]
        return _BrokerPeer(
            name=name,
            client=PcSimClient(host=udp_host, port=udp_port, timeout=udp_timeout_s),
            nodes=nodes,
            filters=filters,
            origin=origin,
        )

    def _build_peers(self, ecus: List[EcuConfig], can_clients: List[CanClientConfig]) -> List[_BrokerPeer]:
        peers: List[_BrokerPeer] = []
        for ecu in ecus:
            if str(ecu.can_gate).upper() != "PCSIM":
                continue
            peers.append(
                self._peer_from_endpoint(
                    name=ecu.name,
                    udp_host=ecu.udp.host,
                    udp_port=ecu.udp.port,
                    udp_timeout_s=ecu.udp.timeout_s,
                    shared_nodes=ecu.pcsim_shared_can_nodes,
                    rx_filters=ecu.pcsim_rx_filters,
                    origin="ecu",
                )
            )
        for client in can_clients:
            if str(client.can_gate).upper() != "PCSIM":
                continue
            peers.append(
                self._peer_from_endpoint(
                    name=client.name,
                    udp_host=client.udp.host,
                    udp_port=client.udp.port,
                    udp_timeout_s=client.udp.timeout_s,
                    shared_nodes=client.pcsim_shared_can_nodes,
                    rx_filters=client.pcsim_rx_filters,
                    origin="can_client",
                )
            )
        return peers

    @property
    def is_enabled(self) -> bool:
        return self._cfg.can_broker_enabled and len(self._peers) > 0

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
        for peer in self._peers:
            try:
                peer.client.clear_can_broker_tx()
            except Exception:
                pass
        while True:
            try:
                self._rx_queue.get_nowait()
            except Empty:
                break
        self._stop_evt.clear()
        print(
            f"[INFO] CAN broker started with {len(self._peers)} PCSIM peer(s) on ctrl {self._control_port}"
        )
        for idx, peer in enumerate(self._peers, start=1):
            host, port = peer.client.addr
            nodes_txt = "*" if peer.nodes is None else ",".join(str(v) for v in sorted(peer.nodes))
            filters_txt = f"{len(peer.filters)} static"
            if not peer.filters:
                filters_txt += " (runtime RX regs)"
            print(
                f"[BROKER][PEER {idx}] origin={peer.origin} name={peer.name} "
                f"udp={host}:{port} nodes={nodes_txt} filters={filters_txt}"
            )
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

    def _peer_accepts(self, peer: _BrokerPeer, frame: Dict[str, Any]) -> bool:
        node = int(frame.get("node", 0))
        if peer.nodes is not None and node not in peer.nodes:
            return False
        active_filters = peer.filters if peer.filters else peer.dynamic_filters
        if not active_filters:
            return True
        for flt in active_filters:
            if self._frame_matches_filter(frame, flt):
                return True
        return False

    def _peer_reject_reason(self, peer: _BrokerPeer, frame: Dict[str, Any]) -> Optional[str]:
        node = int(frame.get("node", 0))
        if peer.nodes is not None and node not in peer.nodes:
            return f"node {node} not in shared_can_nodes={sorted(peer.nodes)}"

        active_filters = peer.filters if peer.filters else peer.dynamic_filters
        if not active_filters:
            return None

        for flt in active_filters:
            if self._frame_matches_filter(frame, flt):
                return None
        return f"no RX filter match among {len(active_filters)} filter(s)"

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

    def _log_peer_rx_error(self, peer: _BrokerPeer, exc: Exception) -> None:
        now_s = time.monotonic()
        err_msg = str(exc)
        should_log = (now_s - peer.last_error_log_s) >= self._peer_error_log_period_s
        if err_msg != peer.last_error_msg:
            should_log = True
        if not should_log:
            return

        host, port = peer.client.addr
        if isinstance(exc, TimeoutError) and "UDP peer reset while sending" in err_msg:
            print(
                f"[BROKER][WARN] peer '{peer.name}' ({peer.origin}, {host}:{port}) unreachable: {err_msg}. "
                "Check that the external PCSIM endpoint is running and listening on this UDP port."
            )
        else:
            print(
                f"[BROKER][WARN] peer '{peer.name}' ({peer.origin}, {host}:{port}) RX error: {err_msg}"
            )
        peer.last_error_log_s = now_s
        peer.last_error_msg = err_msg

    def _log_route_warn(self, key: str, msg: str) -> None:
        now_s = time.monotonic()
        last_s = self._last_route_warn_s.get(key, 0.0)
        if (now_s - last_s) < self._route_warn_log_period_s:
            return
        self._last_route_warn_s[key] = now_s
        print(msg)

    def _log_route_info(self, key: str, msg: str) -> None:
        now_s = time.monotonic()
        last_s = self._last_route_info_s.get(key, 0.0)
        if (now_s - last_s) < self._route_info_log_period_s:
            return
        self._last_route_info_s[key] = now_s
        print(msg)

    def _peer_rx_loop(self, src: _BrokerPeer) -> None:
        while not self._stop_evt.is_set():
            try:
                now_s = time.monotonic()
                if (now_s - src.last_rx_refresh_s) >= self._rx_refresh_period_s:
                    try:
                        src.dynamic_filters = self._filters_from_runtime_regs(
                            src.client.dump_can_rx_reg_burst(128)
                        )
                        src.last_rx_refresh_s = now_s
                    except Exception:
                        pass

                frames = src.client.pop_can_broker_tx_burst(self._max_pop)
                if not frames:
                    continue
                self._add_stats(rx_frames=len(frames))
                for frame in frames:
                    try:
                        print(f"from {src.name}, get {frame}")
                        self._rx_queue.put_nowait((src.name, frame))
                    except Full:
                        self._add_stats(dropped_frames=1)
                        break
            except Exception as e:
                self._log_peer_rx_error(src, e)
                self._add_stats(cycle_errors=1)
                if self._poll_sleep_s > 0.0:
                    time.sleep(self._poll_sleep_s)

    def _run(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.perf_counter()
            try:
                src_name, frame = self._rx_queue.get(timeout=0.01)
                try:
                    node = int(frame.get("node", 0))
                    can_id = int(frame.get("can_id", 0))
                    is_extended = bool(frame.get("is_extended", True))
                    if (can_id > 0x7FF) and (not is_extended):
                        self._log_route_warn(
                            f"ext_fix:{src_name}",
                            f"[BROKER][WARN] source '{src_name}' frame id=0x{can_id:X} with ext=0. "
                            "Forcing ext=1 because CAN ID is > 0x7FF.",
                        )
                        is_extended = True
                    dlc = int(frame.get("dlc", len(list(frame.get("data", [])))))
                    if dlc < 0:
                        dlc = 0
                    data = [int(v) & 0xFF for v in list(frame.get("data", []))[:dlc]]
                    if len(data) > 8:
                        self._log_route_warn(
                            f"fd_truncate:{src_name}",
                            f"[BROKER][WARN] source '{src_name}' sent DLC={len(data)} (>8). "
                            "Truncating to 8 bytes for PCSIM inject.",
                        )
                        data = data[:8]
                    frame_norm: Dict[str, Any] = {
                        "node": node,
                        "can_id": can_id,
                        "is_extended": is_extended,
                        "data": data,
                    }
                except Exception as e:
                    self._log_route_warn(
                        f"bad_frame:{src_name}",
                        f"[BROKER][WARN] invalid frame from '{src_name}' dropped: {e}",
                    )
                    self._add_stats(dropped_frames=1, cycle_errors=1)
                    continue
                routed = 0
                injected = 0
                dropped = 0
                per_dst_count: Dict[str, int] = {}
                for dst in self._peers:
                    if dst.name == src_name:
                        continue
                    reject_reason = self._peer_reject_reason(dst, frame_norm)
                    if reject_reason is not None:
                        self._log_route_warn(
                            f"reject:{src_name}:{dst.name}",
                            f"[BROKER][WARN] rejected src='{src_name}' -> dst='{dst.name}' "
                            f"node={node} id=0x{can_id:X} ext={int(is_extended)}: {reject_reason}",
                        )
                        continue
                    cnt = per_dst_count.get(dst.name, 0)
                    if cnt >= self._max_inject:
                        dropped += 1
                        continue
                    try:
                        dst.client.inject_can_ex(
                            node,
                            can_id,
                            is_extended,
                            data,
                        )
                        self._log_route_info(
                            f"inject_ok:{src_name}:{dst.name}:{node}:{can_id}:{int(is_extended)}",
                            f"[BROKER][ROUTE] src='{src_name}' -> dst='{dst.name}' "
                            f"node={node} id=0x{can_id:X} ext={int(is_extended)} dlc={len(data)}",
                        )
                        per_dst_count[dst.name] = cnt + 1
                        routed += 1
                        injected += 1
                    except Exception as e:
                        self._log_route_warn(
                            f"inject_err:{src_name}:{dst.name}",
                            f"[BROKER][WARN] inject failed src='{src_name}' -> dst='{dst.name}' "
                            f"node={node} id=0x{can_id:X} ext={int(is_extended)}: {e}",
                        )
                        dropped += 1
                if routed == 0 and dropped == 0:
                    self._log_route_warn(
                        f"no_dst:{src_name}",
                        f"[BROKER][WARN] no destination accepted frame from '{src_name}' "
                        f"(node={node}, id=0x{can_id:X}, ext={int(is_extended)}). "
                        "Check shared_can_nodes and RX filters.",
                    )
                dt_ms = int((time.perf_counter() - t0) * 1000.0)
                self._add_stats(
                    routed_frames=routed,
                    injected_frames=injected,
                    dropped_frames=dropped,
                )
                with self._stats_lock:
                    self._stats["last_cycle_ms"] = dt_ms
            except Empty:
                pass
            except Exception:
                self._add_stats(cycle_errors=1)
            self._process_control_requests()

            if self._poll_sleep_s > 0.0:
                time.sleep(self._poll_sleep_s)

        print("[INFO] CAN broker stopped")
