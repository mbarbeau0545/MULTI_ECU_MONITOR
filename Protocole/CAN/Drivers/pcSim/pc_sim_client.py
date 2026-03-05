import socket
from typing import Dict, Iterable, List, Optional, Tuple


class PcSimClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 19090, timeout: float = 0.5):
        self.addr = (host, port)
        self.timeout = timeout

    def _send(self, command: str) -> str:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout)
            sock.sendto(command.encode("ascii"), self.addr)
            try:
                data, _ = sock.recvfrom(16384)
            except ConnectionResetError as exc:
                # Windows UDP may raise WinError 10054 when peer is not ready.
                raise TimeoutError(f"UDP peer reset while sending '{command}'") from exc
            return data.decode("ascii", errors="replace").strip()

    @staticmethod
    def _parse_tokens(response: str) -> List[str]:
        tokens = response.strip().split()
        if not tokens:
            raise RuntimeError("empty response")
        if tokens[0] != "OK":
            raise RuntimeError(response)
        return tokens

    @staticmethod
    def _parse_rc(response: str) -> int:
        tokens = PcSimClient._parse_tokens(response)
        if "RC" not in tokens:
            return 0
        idx = tokens.index("RC")
        if (idx + 1) >= len(tokens):
            raise RuntimeError(f"invalid RC response: {response}")
        return int(tokens[idx + 1], 0)

    @staticmethod
    def _parse_key_value(response: str, key: str) -> str:
        tokens = PcSimClient._parse_tokens(response)
        if key not in tokens:
            raise RuntimeError(f"missing key '{key}' in response: {response}")
        idx = tokens.index(key)
        if (idx + 1) >= len(tokens):
            raise RuntimeError(f"missing value for key '{key}' in response: {response}")
        return tokens[idx + 1]

    def ping(self) -> str:
        return self._send("PING")

    def get_all(self) -> str:
        return self._send("GET_ALL")

    def set_ana(self, idx: int, value: float) -> str:
        return self._send(f"SET_ANA {idx} {value}")

    def get_ana(self, idx: int) -> float:
        rsp = self._send(f"GET_ANA {idx}")
        return float(self._parse_key_value(rsp, "VAL"))

    def set_pwm(self, idx: int, duty: int) -> str:
        return self._send(f"SET_PWM {idx} {duty}")

    def get_pwm(self, idx: int) -> int:
        rsp = self._send(f"GET_PWM {idx}")
        return int(self._parse_key_value(rsp, "VAL"), 0)

    def set_pwm_freq(self, idx: int, frequency_hz: float) -> str:
        return self._send(f"SET_PWM_FREQ {idx} {frequency_hz}")

    def get_pwm_freq(self, idx: int) -> float:
        rsp = self._send(f"GET_PWM_FREQ {idx}")
        return float(self._parse_key_value(rsp, "VAL"))

    def set_pwm_pulses(self, idx: int, pulses: int) -> str:
        return self._send(f"SET_PWM_PULSES {idx} {pulses}")

    def get_pwm_pulses(self, idx: int) -> int:
        rsp = self._send(f"GET_PWM_PULSES {idx}")
        return int(self._parse_key_value(rsp, "VAL"), 0)

    def set_in_dig(self, idx: int, value: int) -> str:
        return self._send(f"SET_IN_DIG {idx} {value}")

    def get_in_dig(self, idx: int) -> int:
        rsp = self._send(f"GET_IN_DIG {idx}")
        return int(self._parse_key_value(rsp, "VAL"), 0)

    def trigger_in_evnt(self, idx: int) -> str:
        return self._send(f"TRIG_IN_EVNT {idx}")

    def set_out_dig(self, idx: int, value: int) -> str:
        return self._send(f"SET_OUT_DIG {idx} {value}")

    def get_out_dig(self, idx: int) -> int:
        rsp = self._send(f"GET_OUT_DIG {idx}")
        return int(self._parse_key_value(rsp, "VAL"), 0)

    def set_in_freq(self, idx: int, frequency_hz: float) -> str:
        return self._send(f"SET_IN_FREQ {idx} {frequency_hz}")

    def get_in_freq(self, idx: int) -> float:
        rsp = self._send(f"GET_IN_FREQ {idx}")
        return float(self._parse_key_value(rsp, "VAL"))

    def set_enc_pos(self, idx: int, absolute: float, relative: float) -> str:
        return self._send(f"SET_ENC_POS {idx} {absolute} {relative}")

    def get_enc_pos(self, idx: int) -> Tuple[float, float]:
        rsp = self._send(f"GET_ENC_POS {idx}")
        abs_val = float(self._parse_key_value(rsp, "ABS"))
        rel_val = float(self._parse_key_value(rsp, "REL"))
        return abs_val, rel_val

    def set_enc_speed(self, idx: int, speed: float) -> str:
        return self._send(f"SET_ENC_SPEED {idx} {speed}")

    def get_enc_speed(self, idx: int) -> float:
        rsp = self._send(f"GET_ENC_SPEED {idx}")
        return float(self._parse_key_value(rsp, "VAL"))

    def set_enc_map(self, idx: int, sig_pwm: int, pulses_per_revolution: float, sig_dir: int) -> str:
        return self._send(f"SET_ENC_MAP {idx} {sig_pwm} {pulses_per_revolution} {sig_dir}")

    def inject_can(self, node: int, can_id: int, payload: Iterable[int]) -> str:
        return self.inject_can_ex(node, can_id, True, payload)

    def inject_can_ex(self, node: int, can_id: int, is_extended: bool, payload: Iterable[int]) -> str:
        data: List[int] = [int(v) & 0xFF for v in payload]
        if len(data) > 8:
            raise ValueError("payload max length is 8")
        bytes_str = " ".join(str(v) for v in data)
        ext_u8 = 1 if is_extended else 0
        return self._send(f"INJECT_CAN_EX {node} {can_id} {ext_u8} {len(data)} {bytes_str}")

    def get_can_tx_count(self) -> int:
        rsp = self._send("GET_CAN_TX_COUNT")
        return int(self._parse_key_value(rsp, "COUNT"), 0)

    def get_can_broker_tx_count(self) -> int:
        rsp = self._send("GET_CAN_BROKER_TX_COUNT")
        return int(self._parse_key_value(rsp, "COUNT"), 0)

    def get_can_rx_reg_count(self) -> int:
        rsp = self._send("GET_CAN_RX_REG_COUNT")
        return int(self._parse_key_value(rsp, "COUNT"), 0)

    def clear_can_tx(self) -> int:
        rsp = self._send("CLEAR_CAN_TX")
        return self._parse_rc(rsp)

    def clear_can_broker_tx(self) -> int:
        rsp = self._send("CLEAR_CAN_BROKER_TX")
        return self._parse_rc(rsp)

    def pop_can_tx(self) -> Optional[Dict[str, object]]:
        rsp = self._send("POP_CAN_TX")
        rc = self._parse_rc(rsp)
        if rc != 0:
            return None

        tokens = self._parse_tokens(rsp)

        def get_int(key: str) -> int:
            return int(self._parse_key_value(rsp, key), 0)

        data: List[int] = []
        if "DATA" in tokens:
            data_idx = tokens.index("DATA") + 1
            data = [int(tok, 0) for tok in tokens[data_idx:]]

        return {
            "timestamp_ms": get_int("TS"),
            "node": get_int("NODE"),
            "can_id": get_int("ID"),
            "is_extended": bool(get_int("EXT")),
            "dlc": get_int("DLC"),
            "data": data,
        }

    def pop_can_tx_burst(self, max_frames: int = 10) -> List[Dict[str, object]]:
        if max_frames < 1:
            return []
        rsp = self._send(f"POP_CAN_TX_BURST {max_frames}")
        rc = self._parse_rc(rsp)
        if rc != 0:
            return []

        tokens = self._parse_tokens(rsp)
        frames: List[Dict[str, object]] = []
        idx = 0
        while idx < len(tokens):
            if tokens[idx] != "FRAME":
                idx += 1
                continue
            # FRAME TS <ts> NODE <node> ID <id> EXT <ext> DLC <dlc> DATA <b0>..<bN-1>
            if idx + 12 >= len(tokens):
                break
            if (tokens[idx + 1] != "TS"
                or tokens[idx + 3] != "NODE"
                or tokens[idx + 5] != "ID"
                or tokens[idx + 7] != "EXT"
                or tokens[idx + 9] != "DLC"
                or tokens[idx + 11] != "DATA"):
                idx += 1
                continue

            ts = int(tokens[idx + 2], 0)
            node = int(tokens[idx + 4], 0)
            can_id = int(tokens[idx + 6], 0)
            is_ext = bool(int(tokens[idx + 8], 0))
            dlc = int(tokens[idx + 10], 0)
            if dlc < 0:
                dlc = 0
            data_start = idx + 12
            data_end = min(len(tokens), data_start + dlc)
            data = [int(tok, 0) & 0xFF for tok in tokens[data_start:data_end]]

            frames.append(
                {
                    "timestamp_ms": ts,
                    "node": node,
                    "can_id": can_id,
                    "is_extended": is_ext,
                    "dlc": dlc,
                    "data": data,
                }
            )
            idx = data_end

        return frames

    def pop_can_broker_tx_burst(self, max_frames: int = 10) -> List[Dict[str, object]]:
        if max_frames < 1:
            return []
        rsp = self._send(f"POP_CAN_BROKER_TX_BURST {max_frames}")
        rc = self._parse_rc(rsp)
        if rc != 0:
            return []
        # Same payload format as POP_CAN_TX_BURST
        tokens = self._parse_tokens(rsp)
        frames: List[Dict[str, object]] = []
        idx = 0
        while idx < len(tokens):
            if tokens[idx] != "FRAME":
                idx += 1
                continue
            if idx + 12 >= len(tokens):
                break
            if (tokens[idx + 1] != "TS"
                or tokens[idx + 3] != "NODE"
                or tokens[idx + 5] != "ID"
                or tokens[idx + 7] != "EXT"
                or tokens[idx + 9] != "DLC"
                or tokens[idx + 11] != "DATA"):
                idx += 1
                continue
            ts = int(tokens[idx + 2], 0)
            node = int(tokens[idx + 4], 0)
            can_id = int(tokens[idx + 6], 0)
            is_ext = bool(int(tokens[idx + 8], 0))
            dlc = int(tokens[idx + 10], 0)
            if dlc < 0:
                dlc = 0
            data_start = idx + 12
            data_end = min(len(tokens), data_start + dlc)
            data = [int(tok, 0) & 0xFF for tok in tokens[data_start:data_end]]
            frames.append(
                {
                    "timestamp_ms": ts,
                    "node": node,
                    "can_id": can_id,
                    "is_extended": is_ext,
                    "dlc": dlc,
                    "data": data,
                }
            )
            idx = data_end
        return frames

    def dump_can_rx_reg_burst(self, max_regs: int = 64) -> List[Dict[str, object]]:
        if max_regs < 1:
            return []
        rsp = self._send(f"DUMP_CAN_RX_REG_BURST {max_regs}")
        rc = self._parse_rc(rsp)
        if rc != 0:
            return []

        tokens = self._parse_tokens(rsp)
        regs: List[Dict[str, object]] = []
        idx = 0
        while idx < len(tokens):
            if tokens[idx] != "REG":
                idx += 1
                continue
            # REG NODE <node> ID <id> MASK <mask> EXT <ext>
            if idx + 8 >= len(tokens):
                break
            if (tokens[idx + 1] != "NODE"
                or tokens[idx + 3] != "ID"
                or tokens[idx + 5] != "MASK"
                or tokens[idx + 7] != "EXT"):
                idx += 1
                continue
            regs.append(
                {
                    "node": int(tokens[idx + 2], 0),
                    "can_id": int(tokens[idx + 4], 0),
                    "mask": int(tokens[idx + 6], 0),
                    "is_extended": bool(int(tokens[idx + 8], 0)),
                }
            )
            idx += 9
        return regs
