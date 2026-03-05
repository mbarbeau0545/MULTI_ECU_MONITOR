"""
    @file        pcSimCanMngmt.py
    @brief       CANInterface implementation over PC_SIM UDP bridge.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from queue import Empty
from typing import Any, Dict, Optional
from typing import List

from Library.ModuleLog import log

from ..Drivers.pcSim.pc_sim_client import PcSimClient
from .AbstractCAN import (
    CANInterface,
    CanModuleNotInitError,
    MsgType,
    StructCANMsg,
)


@dataclass
class PcSimCanConfig:
    host: str = "127.0.0.1"
    port: int = 19090
    node: int = 0
    timeout_s: float = 0.001
    poll_sleep_s: float = 0.00005
    max_pop_per_cycle: int = 128
    clear_can_tx_on_connect: bool = True


class PcSimCanMngmt(CANInterface):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client: Optional[PcSimClient] = None
        self._cfg: PcSimCanConfig = PcSimCanConfig()
        self._last_connect_kwargs: Dict[str, Any] = {}
        self._last_send_warn_ts: float = 0.0
        self._last_rx_warn_ts: float = 0.0

    def _build_config(self, kwargs: Dict[str, Any]) -> PcSimCanConfig:
        cfg = PcSimCanConfig()
        device_port = kwargs.get("device_port")

        host = kwargs.get("host", cfg.host)
        port = kwargs.get("port", cfg.port)
        node = kwargs.get("node", cfg.node)
        timeout_s = kwargs.get("timeout_s", kwargs.get("timeout", cfg.timeout_s))
        poll_sleep_s = kwargs.get("poll_sleep_s", cfg.poll_sleep_s)
        max_pop_per_cycle = kwargs.get("max_pop_per_cycle", cfg.max_pop_per_cycle)
        clear_on_connect = kwargs.get("clear_can_tx_on_connect", cfg.clear_can_tx_on_connect)

        if isinstance(device_port, dict):
            host = device_port.get("host", device_port.get("ip", host))
            port = device_port.get("port", port)
            node = device_port.get("node", node)
        elif isinstance(device_port, str):
            if ":" in device_port:
                split = device_port.split(":", 1)
                host = split[0] or host
                if split[1]:
                    port = int(split[1], 0)
            elif device_port.strip():
                host = device_port.strip()
        elif isinstance(device_port, int):
            port = int(device_port)

        return PcSimCanConfig(
            host=str(host),
            port=int(port),
            node=int(node),
            timeout_s=float(timeout_s),
            poll_sleep_s=float(poll_sleep_s),
            max_pop_per_cycle=max(1, int(max_pop_per_cycle)),
            clear_can_tx_on_connect=bool(clear_on_connect),
        )

    def connect(self, **kwargs) -> None:
        if kwargs:
            self._last_connect_kwargs = dict(kwargs)
        elif self._last_connect_kwargs:
            kwargs = dict(self._last_connect_kwargs)

        self._cfg = self._build_config(kwargs)
        self._client = PcSimClient(host=self._cfg.host, port=self._cfg.port, timeout=self._cfg.timeout_s)

        # Validate link early.
        self._client.ping()

        if self._cfg.clear_can_tx_on_connect:
            self._client.clear_can_tx()

        self.reset_stats()
        self.is_init = True

    def disconnect(self) -> None:
        if not self.is_init:
            raise CanModuleNotInitError("Instance Not Init, please use Connect Method first")

        self.receive_queue_stop()
        if self._rx_thread is not None:
            self._rx_thread.join(timeout=1.0)

        self._client = None
        self.is_init = False

    def send(self, f_frame: StructCANMsg) -> None:
        if not self.is_init or self._client is None:
            raise CanModuleNotInitError("Instance Not Init, please use Connect Method first")

        dlc = int(f_frame.length)
        if dlc < 0:
            dlc = 0
        if dlc > self._MC_DLC_8:
            dlc = self._MC_DLC_8

        payload = [int(v) & 0xFF for v in list(f_frame.data)[:dlc]]
        is_extended = f_frame.msgType != MsgType.CAN_MNGMT_MSG_STANDARD
        can_id = int(f_frame.id)

        # PC_SIM INJECT_CAN currently supports only an "extended" flag.
        if not is_extended:
            can_id &= 0x7FF
        else:
            can_id &= 0x1FFFFFFF

        # While debugging the server, UDP replies can timeout; do not propagate
        # this to the UI thread. Drop the frame without retry to avoid duplicates.
        try:
            self._client.inject_can(self._cfg.node, can_id, payload)
        except TimeoutError:
            now = time.time()
            if (now - self._last_send_warn_ts) > 1.0:
                print("[WARNING] PC_SIM timeout on CAN send (server paused/debug?). Frame dropped.")
                self._last_send_warn_ts = now
            return
        except Exception as exc:
            now = time.time()
            if (now - self._last_send_warn_ts) > 1.0:
                print(f"[WARNING] PC_SIM send error: {exc}")
                self._last_send_warn_ts = now
            return

        if self.enable_log:
            try:
                self.make_log.LCF_SetMsgLog(
                    log.INFO,
                    "Snd  : 0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X"
                    % (
                        can_id,
                        payload[0] if len(payload) > 0 else 0,
                        payload[1] if len(payload) > 1 else 0,
                        payload[2] if len(payload) > 2 else 0,
                        payload[3] if len(payload) > 3 else 0,
                        payload[4] if len(payload) > 4 else 0,
                        payload[5] if len(payload) > 5 else 0,
                        payload[6] if len(payload) > 6 else 0,
                        payload[7] if len(payload) > 7 else 0,
                    ),
                )
            except Exception:
                pass

    def receive_poll(self) -> StructCANMsg:
        if not self.is_init or self._client is None:
            raise CanModuleNotInitError("Instance Not Init, please use Connect Method first")

        try:
            frame = self._client.pop_can_tx()
        except TimeoutError:
            # Consider timeout as "no frame available" to keep app responsive.
            return StructCANMsg()
        except Exception as exc:
            now = time.time()
            if (now - self._last_rx_warn_ts) > 1.0:
                print(f"[WARNING] PC_SIM receive error: {exc}")
                self._last_rx_warn_ts = now
            return StructCANMsg()

        if frame is None:
            return StructCANMsg()

        dlc = int(frame.get("dlc", 0))
        if dlc < 0:
            dlc = 0
        if dlc > self._MC_DLC_8:
            dlc = self._MC_DLC_8
        data = [int(v) & 0xFF for v in list(frame.get("data", []))[:dlc]]
        msg_type = MsgType.CAN_MNGMT_MSG_EXTENDED if bool(frame.get("is_extended", True)) else MsgType.CAN_MNGMT_MSG_STANDARD

        msg = StructCANMsg(
            id=int(frame.get("can_id", 0)),
            msgType=msg_type,
            length=dlc,
            data=data,
            timestamp=int(frame.get("timestamp_ms", int(time.time() * 1000))),
        )
        self._stats["low_rx_total"] += 1
        return msg

    def receive_poll_burst(self, max_frames: int) -> List[StructCANMsg]:
        if not self.is_init or self._client is None:
            raise CanModuleNotInitError("Instance Not Init, please use Connect Method first")

        out: List[StructCANMsg] = []
        try:
            frames = self._client.pop_can_tx_burst(max_frames)
        except TimeoutError:
            return out
        except Exception as exc:
            now = time.time()
            if (now - self._last_rx_warn_ts) > 1.0:
                print(f"[WARNING] PC_SIM receive error: {exc}")
                self._last_rx_warn_ts = now
            return out

        for frame in frames:
            dlc = int(frame.get("dlc", 0))
            if dlc < 0:
                dlc = 0
            if dlc > self._MC_DLC_8:
                dlc = self._MC_DLC_8
            data = [int(v) & 0xFF for v in list(frame.get("data", []))[:dlc]]
            msg_type = MsgType.CAN_MNGMT_MSG_EXTENDED if bool(frame.get("is_extended", True)) else MsgType.CAN_MNGMT_MSG_STANDARD
            out.append(
                StructCANMsg(
                    id=int(frame.get("can_id", 0)),
                    msgType=msg_type,
                    length=dlc,
                    data=data,
                    timestamp=int(frame.get("timestamp_ms", int(time.time() * 1000))),
                )
            )
            self._stats["low_rx_total"] += 1

        return out

    def flush(self) -> None:
        if not self.is_init or self._client is None:
            raise CanModuleNotInitError("Instance Not Init, please use Connect Method first")

        self._client.clear_can_tx()
        while not self._receive_queue.empty():
            try:
                self._receive_queue.get_nowait()
            except Exception:
                break

    def _can_reader_cyclic(self) -> None:
        while not self._stop_rx_thread.is_set():
            try:
                got_one = False
                msgs = self.receive_poll_burst(self._cfg.max_pop_per_cycle)
                if len(msgs) > 0:
                    got_one = True
                for msg in msgs:
                    self._queue_rx_item(msg)
                    self._stats["low_queue_total"] += 1
                    if self.enable_log:
                        try:
                            self.make_log.LCF_SetMsgLog(
                                log.INFO,
                                "Rcv  : 0x%03X %02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X"
                                % (
                                    msg.id,
                                    msg.data[0] if len(msg.data) > 0 else 0,
                                    msg.data[1] if len(msg.data) > 1 else 0,
                                    msg.data[2] if len(msg.data) > 2 else 0,
                                    msg.data[3] if len(msg.data) > 3 else 0,
                                    msg.data[4] if len(msg.data) > 4 else 0,
                                    msg.data[5] if len(msg.data) > 5 else 0,
                                    msg.data[6] if len(msg.data) > 6 else 0,
                                    msg.data[7] if len(msg.data) > 7 else 0,
                                ),
                            )
                        except Exception:
                            pass

                if not got_one:
                    time.sleep(self._cfg.poll_sleep_s)
            except TimeoutError:
                # Debug breakpoints on server side are expected to trigger this.
                time.sleep(self._cfg.poll_sleep_s)
            except Exception as exc:
                # Keep the thread alive; reconnect only on persistent hard failures.
                now = time.time()
                if (now - self._last_rx_warn_ts) > 1.0:
                    print(f"[WARNING] PC_SIM RX thread exception: {exc}")
                    self._last_rx_warn_ts = now
                self._try_reconexion()
                time.sleep(self._cfg.poll_sleep_s)

    def get_can_frame(self, f_timeout: float = 0.05) -> StructCANMsg:
        try:
            return self._receive_queue.get(timeout=f_timeout)
        except Empty:
            return StructCANMsg()
