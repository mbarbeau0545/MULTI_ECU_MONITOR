import json
import tempfile
import time
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Tuple

from Protocole.CAN.Drivers.pcSim.pc_sim_client import PcSimClient
from Frame.frameMngmt import FrameMngmt


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


class ScriptApiBackend:
    _HC_CMD_POSITION_CAN_ID = 0x18FF1402

    def __init__(
        self,
        client: PcSimClient,
        stop_event: Event,
        log_cb: Callable[[str], None],
        default_node: int,
        sym_file: Optional[Path] = None,
    ) -> None:
        self._client = client
        self._stop = stop_event
        self._log = log_cb
        self.default_node = default_node
        self._sym_file = Path(sym_file) if sym_file is not None else None
        self._frame_db: Optional[FrameMngmt] = None
        self._symbol_by_can_id_exact: Dict[int, str] = {}
        self._symbol_by_can_id16: Dict[int, List[str]] = {}
        self._latest_signal_sample: Dict[str, Dict[str, Any]] = {}
        self._latest_symbol_signal_sample: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._tmp_cfg_path: Optional[Path] = None
        self._init_sym_database()

    def _init_sym_database(self) -> None:
        if self._sym_file is None or (not self._sym_file.exists()):
            return
        try:
            cfg_data = {
                "signal_cfg": str(self._sym_file),
                "serial_cfg": {
                    "baudrate": 115200,
                    "port_com": "",
                    "frame_len": 0,
                    "is_enable": False,
                    "enable_srl_msg_logg": False,
                    "enable_sig_logg": False,
                    "srl_log_path": str(self._sym_file.parent),
                    "sig_log_path": str(self._sym_file.parent),
                },
                "can_cfg": {
                    "is_enable": False,
                    "gate": "PCSIM",
                    "can_speed_bps": 250000,
                    "device_port": {"host": "127.0.0.1", "port": 19090, "node": 0},
                    "id_to_ignore": [],
                    "enable_can_msg_logg": False,
                    "can_log_path": str(self._sym_file.parent),
                    "sig_log_path": str(self._sym_file.parent),
                },
            }
            with tempfile.NamedTemporaryFile(mode="w", suffix="_script_runtime_prj_cfg.json", delete=False, encoding="utf-8") as tf:
                tf.write(json.dumps(cfg_data, indent=2))
                self._tmp_cfg_path = Path(tf.name)

            self._frame_db = FrameMngmt(str(self._tmp_cfg_path))
            for sym_name, sym in self._frame_db.symbol.items():
                try:
                    msg_id = int(sym.get("msg_id"))
                except Exception:
                    continue
                self._symbol_by_can_id_exact[msg_id] = str(sym_name)
                low16 = msg_id & 0x0000FFFF
                if low16 not in self._symbol_by_can_id16:
                    self._symbol_by_can_id16[low16] = []
                self._symbol_by_can_id16[low16].append(str(sym_name))
            self._log(f"[INFO] SYM loaded: {self._sym_file.name} ({len(self._frame_db.symbol)} symbols)")
        except Exception as exc:
            self._frame_db = None
            self._log(f"[WARN] Cannot load SYM database: {exc}")

    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def sleep_ms(self, delay_ms: int) -> None:
        remaining = max(0, _as_int(delay_ms, 0))
        while remaining > 0 and not self._stop.is_set():
            chunk = min(remaining, 20)
            self._stop.wait(chunk / 1000.0)
            remaining -= chunk

    def sleep_s(self, delay_s: float) -> None:
        self.sleep_ms(int(max(0.0, _as_float(delay_s, 0.0)) * 1000.0))

    def log(self, text: Any) -> None:
        self._log(str(text))

    def set_ana(self, idx: int, value: float) -> None:
        self._client.set_ana(_as_int(idx), _as_float(value))

    def set_pwm(self, idx: int, duty: int) -> None:
        self._client.set_pwm(_as_int(idx), _as_int(duty))

    def set_pwm_freq(self, idx: int, frequency_hz: float) -> None:
        self._client.set_pwm_freq(_as_int(idx), _as_float(frequency_hz))

    def set_in_dig(self, idx: int, value: int) -> None:
        self._client.set_in_dig(_as_int(idx), _as_int(value))

    def trigger_in_evnt(self, idx: int) -> None:
        self._client.trigger_in_evnt(_as_int(idx))

    def set_out_dig(self, idx: int, value: int) -> None:
        self._client.set_out_dig(_as_int(idx), _as_int(value))

    def set_in_freq(self, idx: int, frequency_hz: float) -> None:
        self._client.set_in_freq(_as_int(idx), _as_float(frequency_hz))

    def set_enc_pos(self, idx: int, abs_mrad: float, rel_mrad: float) -> None:
        self._client.set_enc_pos(_as_int(idx), _as_float(abs_mrad), _as_float(rel_mrad))

    def set_enc_speed(self, idx: int, speed_mrad_s: float) -> None:
        self._client.set_enc_speed(_as_int(idx), _as_float(speed_mrad_s))

    def inject_can(self, can_id: int, data: List[int], node: Optional[int] = None, ext: bool = True) -> None:
        tx_node = self.default_node if node is None else _as_int(node)
        self._client.inject_can_ex(tx_node, _as_int(can_id), bool(ext), [(_as_int(v) & 0xFF) for v in data])

    @staticmethod
    def _compute_msg_bit(start_bit: int, bit_idx: int, encoding: str) -> int:
        if str(encoding).upper() == "MOTOROLA":
            byte = start_bit // 8
            bit = start_bit % 8
            msg_bit = (byte * 8 + bit) - bit_idx
            msg_bit = ((7 - (msg_bit // 8)) * 8) + (msg_bit % 8)
            return int(msg_bit)
        return int(start_bit + bit_idx)

    @classmethod
    def _extract_bits(cls, data: List[int], start_bit: int, length: int, encoding: str) -> int:
        bit_val = 0
        for i in range(max(0, int(length))):
            msg_bit = cls._compute_msg_bit(int(start_bit), i, encoding)
            byte_index = msg_bit // 8
            bit_in_byte = msg_bit % 8
            if byte_index < 0 or byte_index >= len(data):
                continue
            bit = (int(data[byte_index]) >> bit_in_byte) & 0x1
            bit_val |= (bit << i)
        return int(bit_val)

    @classmethod
    def _insert_bits(cls, data: List[int], raw_value: int, start_bit: int, length: int, encoding: str) -> None:
        raw = int(raw_value)
        for i in range(max(0, int(length))):
            msg_bit = cls._compute_msg_bit(int(start_bit), i, encoding)
            byte_index = msg_bit // 8
            bit_in_byte = msg_bit % 8
            if byte_index < 0 or byte_index >= len(data):
                continue
            bit = (raw >> i) & 0x1
            if bit:
                data[byte_index] |= (1 << bit_in_byte)
            else:
                data[byte_index] &= ~(1 << bit_in_byte)

    @staticmethod
    def _pack_uint_le(data: List[int], start_bit: int, bit_len: int, raw_value: int) -> None:
        if bit_len <= 0:
            return
        raw = int(raw_value) & ((1 << bit_len) - 1)
        for i in range(bit_len):
            bit = (raw >> i) & 0x1
            frame_bit = start_bit + i
            byte_idx = frame_bit // 8
            bit_idx = frame_bit % 8
            if byte_idx < 0 or byte_idx >= len(data):
                continue
            if bit:
                data[byte_idx] |= (1 << bit_idx)
            else:
                data[byte_idx] &= ~(1 << bit_idx)

    @staticmethod
    def _encode_phys_to_raw(phys_val: float, bit_len: int, factor: float, offset: float) -> int:
        if factor == 0.0:
            return 0
        raw = int(round((phys_val - offset) / factor))
        raw_min = 0
        raw_max = (1 << bit_len) - 1
        if raw < raw_min:
            return raw_min
        if raw > raw_max:
            return raw_max
        return raw

    def send_lgc_hc_cmd_position(
        self,
        pos_a: float,
        pos_b: float,
        knife_rpm: float,
        cntr_knife_rpm: float,
        pos_type: int,
        pos_id: int,
        node: Optional[int] = None,
    ) -> None:
        frame = [0] * 8

        raw_pos_a = self._encode_phys_to_raw(_as_float(pos_a), 12, 1.0, -2048.0)
        raw_pos_b = self._encode_phys_to_raw(_as_float(pos_b), 12, 1.0, -2048.0)
        raw_knife_rpm = self._encode_phys_to_raw(_as_float(knife_rpm), 9, 1.0, 0.0)
        raw_cntr_rpm = self._encode_phys_to_raw(_as_float(cntr_knife_rpm), 9, 1.0, 0.0)
        raw_pos_type = self._encode_phys_to_raw(float(_as_int(pos_type)), 6, 1.0, 0.0)
        raw_pos_id = self._encode_phys_to_raw(float(_as_int(pos_id)), 16, 1.0, 0.0)

        self._pack_uint_le(frame, 0, 12, raw_pos_a)
        self._pack_uint_le(frame, 12, 12, raw_pos_b)
        self._pack_uint_le(frame, 24, 9, raw_knife_rpm)
        self._pack_uint_le(frame, 33, 9, raw_cntr_rpm)
        self._pack_uint_le(frame, 42, 6, raw_pos_type)
        self._pack_uint_le(frame, 48, 16, raw_pos_id)

        tx_node = self.default_node if node is None else _as_int(node)
        self._client.inject_can_ex(tx_node, self._HC_CMD_POSITION_CAN_ID, True, frame)

    def run_hc_position_trajectory(
        self,
        points: List[Any],
        dt_ms: int = 10,
        start_pos_id: int = 1,
        default_pos_type: int = 1,
        default_knife_rpm: float = 20.0,
        default_cntr_knife_rpm: float = 20.0,
        node: Optional[int] = None,
    ) -> None:
        pos_id = _as_int(start_pos_id, 1)
        wait_ms = max(0, _as_int(dt_ms, 10))
        for point in points:
            if self._stop.is_set():
                break
            if isinstance(point, dict):
                pos_a = _as_float(point.get("pos_a", point.get("x", point.get("alpha_a", 0.0))))
                pos_b = _as_float(point.get("pos_b", point.get("y", point.get("alpha_b", 0.0))))
                knife_rpm = _as_float(point.get("knife_rpm", default_knife_rpm))
                cntr_knife_rpm = _as_float(point.get("cntr_knife_rpm", default_cntr_knife_rpm))
                pos_type = _as_int(point.get("pos_type", default_pos_type))
                local_pos_id = _as_int(point.get("pos_id", pos_id))
            elif isinstance(point, (list, tuple)) and len(point) >= 2:
                pos_a = _as_float(point[0])
                pos_b = _as_float(point[1])
                knife_rpm = _as_float(point[2], default_knife_rpm) if len(point) > 2 else default_knife_rpm
                cntr_knife_rpm = _as_float(point[3], default_cntr_knife_rpm) if len(point) > 3 else default_cntr_knife_rpm
                pos_type = _as_int(point[4], default_pos_type) if len(point) > 4 else default_pos_type
                local_pos_id = _as_int(point[5], pos_id) if len(point) > 5 else pos_id
            else:
                continue
            self.send_lgc_hc_cmd_position(pos_a, pos_b, knife_rpm, cntr_knife_rpm, pos_type, local_pos_id, node=node)
            pos_id = (local_pos_id + 1) & 0xFFFF
            self.sleep_ms(wait_ms)

    def list_symbols(self) -> List[str]:
        if self._frame_db is None:
            return []
        return sorted([str(v) for v in self._frame_db.symbol.keys()])

    def list_symbol_signals(self, symbol_name: str, mux_idx: int = 0) -> List[str]:
        if self._frame_db is None:
            return []
        sym = self._frame_db.symbol.get(str(symbol_name))
        if not isinstance(sym, dict):
            return []
        signals = sym.get("signals", {})
        mux_key = str(_as_int(mux_idx, 0))
        if mux_key not in signals:
            return []
        return sorted([str(v) for v in signals[mux_key].keys()])

    def _select_symbol_for_msg_id(self, msg_id: int) -> Optional[str]:
        sym = self._symbol_by_can_id_exact.get(int(msg_id))
        if sym is not None:
            return sym
        candidates = self._symbol_by_can_id16.get(int(msg_id) & 0x0000FFFF, [])
        if len(candidates) > 0:
            return candidates[0]
        return None

    def _decode_can_frame_to_cache(self, msg_id: int, data: List[int], timestamp_ms: int = 0) -> None:
        if self._frame_db is None:
            return
        sym_name = self._select_symbol_for_msg_id(msg_id)
        if sym_name is None:
            return
        sym = self._frame_db.symbol.get(sym_name)
        if not isinstance(sym, dict):
            return

        mux_idx = "0"
        mux_info = sym.get("mux_info", {})
        if isinstance(mux_info, dict) and len(mux_info) > 0:
            mux_raw = self._extract_bits(
                data,
                int(mux_info.get("start_bit", 0)),
                int(mux_info.get("length", 0)),
                str(mux_info.get("encoding", "INTEL")),
            )
            mux_idx = str(mux_raw)

        sig_map = sym.get("signals", {}).get(mux_idx, {})
        if not isinstance(sig_map, dict):
            return

        for sig_name, start_bit in sig_map.items():
            sig_cfg = self._frame_db.signals.get(sig_name, {})
            bit_len = int(sig_cfg.get("length", 0))
            encoding = str(sig_cfg.get("encoding", "INTEL"))
            factor = _as_float(sig_cfg.get("factor", 1.0), 1.0)
            offset = _as_float(sig_cfg.get("offset", 0.0), 0.0)
            enum_name = sig_cfg.get("enum")
            raw_value = self._extract_bits(data, int(start_bit), bit_len, encoding)

            if enum_name and enum_name in self._frame_db.enum:
                enum_map = {int(v[0]): v[1] for v in self._frame_db.enum[enum_name]}
                value = enum_map.get(raw_value, raw_value)
            else:
                value = (raw_value * factor) + offset

            sample = {
                "symbol": str(sym_name),
                "signal": str(sig_name),
                "raw": int(raw_value),
                "value": value,
                "msg_id": int(msg_id),
                "timestamp_ms": int(timestamp_ms),
            }
            self._latest_signal_sample[str(sig_name)] = sample
            self._latest_symbol_signal_sample[(str(sym_name), str(sig_name))] = sample

    def _pump_rx_and_decode(self, max_frames: int = 128) -> int:
        frames = self._client.pop_can_tx_burst(max(1, _as_int(max_frames, 128)))
        count = 0
        for frame in frames:
            msg_id = _as_int(frame.get("can_id", 0), 0)
            payload = [(_as_int(v) & 0xFF) for v in frame.get("data", [])]
            ts = _as_int(frame.get("timestamp_ms", 0), 0)
            self._decode_can_frame_to_cache(msg_id, payload, ts)
            count += 1
        return count

    def get_signal_sample(self, signal_name: str, timeout_ms: int = 0) -> Optional[Dict[str, Any]]:
        target = str(signal_name)
        deadline = (time.monotonic() + (max(0, _as_int(timeout_ms, 0)) / 1000.0))
        while True:
            self._pump_rx_and_decode(128)
            sample = self._latest_signal_sample.get(target)
            if sample is not None:
                return dict(sample)
            if timeout_ms <= 0 or time.monotonic() >= deadline or self._stop.is_set():
                return None
            self.sleep_ms(10)

    def get_symbol_signal_sample(self, symbol_name: str, signal_name: str, timeout_ms: int = 0) -> Optional[Dict[str, Any]]:
        key = (str(symbol_name), str(signal_name))
        deadline = (time.monotonic() + (max(0, _as_int(timeout_ms, 0)) / 1000.0))
        while True:
            self._pump_rx_and_decode(128)
            sample = self._latest_symbol_signal_sample.get(key)
            if sample is not None:
                return dict(sample)
            if timeout_ms <= 0 or time.monotonic() >= deadline or self._stop.is_set():
                return None
            self.sleep_ms(10)

    def get_signal(self, signal_name: str, timeout_ms: int = 0) -> Optional[Any]:
        sample = self.get_signal_sample(signal_name, timeout_ms=timeout_ms)
        if sample is None:
            return None
        return sample.get("value")

    def send_symbol_msg(
        self,
        symbol_name: str,
        signal_values: Dict[str, Any],
        mux_idx: int = 0,
        node: Optional[int] = None,
        ext: bool = True,
    ) -> None:
        if self._frame_db is None:
            raise RuntimeError("SYM database is not available")
        sym = self._frame_db.symbol.get(str(symbol_name))
        if not isinstance(sym, dict):
            raise KeyError(f"Unknown symbol '{symbol_name}'")
        mux_key = str(_as_int(mux_idx, 0))
        sig_map = sym.get("signals", {}).get(mux_key, {})
        if not isinstance(sig_map, dict):
            raise KeyError(f"No mux '{mux_key}' for symbol '{symbol_name}'")

        msg_id = int(sym.get("msg_id", 0))
        msg_len = _as_int(sym.get("msg_len", 8), 8)
        if msg_len <= 0:
            msg_len = 8
        payload = [0] * msg_len
        values = dict(signal_values) if isinstance(signal_values, dict) else {}

        for sig_name, start_bit in sig_map.items():
            if sig_name not in values:
                continue
            sig_cfg = self._frame_db.signals.get(sig_name, {})
            bit_len = int(sig_cfg.get("length", 0))
            encoding = str(sig_cfg.get("encoding", "INTEL"))
            factor = _as_float(sig_cfg.get("factor", 1.0), 1.0)
            offset = _as_float(sig_cfg.get("offset", 0.0), 0.0)
            raw = self._encode_phys_to_raw(_as_float(values[sig_name]), bit_len, factor, offset)
            self._insert_bits(payload, raw, int(start_bit), bit_len, encoding)

        tx_node = self.default_node if node is None else _as_int(node)
        self._client.inject_can_ex(tx_node, int(msg_id), bool(ext), payload[:8])

        # Update local cache with what we just sent.
        self._decode_can_frame_to_cache(int(msg_id), payload[:8], 0)

    @staticmethod
    def u16le(value: int) -> List[int]:
        v = _as_int(value) & 0xFFFF
        return [v & 0xFF, (v >> 8) & 0xFF]

    @staticmethod
    def s16le(value: int) -> List[int]:
        v = _as_int(value)
        if v < 0:
            v = (1 << 16) + v
        v &= 0xFFFF
        return [v & 0xFF, (v >> 8) & 0xFF]


_BACKEND: Optional[ScriptApiBackend] = None


def set_backend(backend: ScriptApiBackend) -> None:
    global _BACKEND
    _BACKEND = backend


def clear_backend() -> None:
    global _BACKEND
    _BACKEND = None


def _api() -> ScriptApiBackend:
    if _BACKEND is None:
        raise RuntimeError("Script runtime API backend is not initialized")
    return _BACKEND


def stop_requested() -> bool:
    return _api().stop_requested()


def sleep_ms(delay_ms: int) -> None:
    _api().sleep_ms(delay_ms)


def sleep_s(delay_s: float) -> None:
    _api().sleep_s(delay_s)


def log(text: Any) -> None:
    _api().log(text)


def set_ana(idx: int, value: float) -> None:
    _api().set_ana(idx, value)


def set_pwm(idx: int, duty: int) -> None:
    _api().set_pwm(idx, duty)


def set_pwm_freq(idx: int, frequency_hz: float) -> None:
    _api().set_pwm_freq(idx, frequency_hz)


def set_in_dig(idx: int, value: int) -> None:
    _api().set_in_dig(idx, value)


def trigger_in_evnt(idx: int) -> None:
    _api().trigger_in_evnt(idx)


def set_out_dig(idx: int, value: int) -> None:
    _api().set_out_dig(idx, value)


def set_in_freq(idx: int, frequency_hz: float) -> None:
    _api().set_in_freq(idx, frequency_hz)


def set_enc_pos(idx: int, abs_mrad: float, rel_mrad: float) -> None:
    _api().set_enc_pos(idx, abs_mrad, rel_mrad)


def set_enc_speed(idx: int, speed_mrad_s: float) -> None:
    _api().set_enc_speed(idx, speed_mrad_s)


def inject_can(can_id: int, data: List[int], node: Optional[int] = None, ext: bool = True) -> None:
    _api().inject_can(can_id, data, node=node, ext=ext)


def list_symbols() -> List[str]:
    return _api().list_symbols()


def list_symbol_signals(symbol_name: str, mux_idx: int = 0) -> List[str]:
    return _api().list_symbol_signals(symbol_name, mux_idx=mux_idx)


def send_symbol_msg(
    symbol_name: str,
    signal_values: Dict[str, Any],
    mux_idx: int = 0,
    node: Optional[int] = None,
    ext: bool = True,
) -> None:
    _api().send_symbol_msg(symbol_name, signal_values, mux_idx=mux_idx, node=node, ext=ext)


def get_signal_sample(signal_name: str, timeout_ms: int = 0) -> Optional[Dict[str, Any]]:
    return _api().get_signal_sample(signal_name, timeout_ms=timeout_ms)


def get_symbol_signal_sample(symbol_name: str, signal_name: str, timeout_ms: int = 0) -> Optional[Dict[str, Any]]:
    return _api().get_symbol_signal_sample(symbol_name, signal_name, timeout_ms=timeout_ms)


def get_signal(signal_name: str, timeout_ms: int = 0) -> Optional[Any]:
    return _api().get_signal(signal_name, timeout_ms=timeout_ms)


def send_lgc_hc_cmd_position(
    pos_a: float,
    pos_b: float,
    knife_rpm: float,
    cntr_knife_rpm: float,
    pos_type: int,
    pos_id: int,
    node: Optional[int] = None,
) -> None:
    _api().send_lgc_hc_cmd_position(pos_a, pos_b, knife_rpm, cntr_knife_rpm, pos_type, pos_id, node=node)


def run_hc_position_trajectory(
    points: List[Any],
    dt_ms: int = 10,
    start_pos_id: int = 1,
    default_pos_type: int = 1,
    default_knife_rpm: float = 20.0,
    default_cntr_knife_rpm: float = 20.0,
    node: Optional[int] = None,
) -> None:
    _api().run_hc_position_trajectory(
        points,
        dt_ms=dt_ms,
        start_pos_id=start_pos_id,
        default_pos_type=default_pos_type,
        default_knife_rpm=default_knife_rpm,
        default_cntr_knife_rpm=default_cntr_knife_rpm,
        node=node,
    )


def u16le(value: int) -> List[int]:
    return ScriptApiBackend.u16le(value)


def s16le(value: int) -> List[int]:
    return ScriptApiBackend.s16le(value)


__all__ = [
    "stop_requested",
    "sleep_ms",
    "sleep_s",
    "log",
    "set_ana",
    "set_pwm",
    "set_pwm_freq",
    "set_in_dig",
    "trigger_in_evnt",
    "set_out_dig",
    "set_in_freq",
    "set_enc_pos",
    "set_enc_speed",
    "inject_can",
    "list_symbols",
    "list_symbol_signals",
    "send_symbol_msg",
    "get_signal_sample",
    "get_symbol_signal_sample",
    "get_signal",
    "send_lgc_hc_cmd_position",
    "run_hc_position_trajectory",
    "u16le",
    "s16le",
]
