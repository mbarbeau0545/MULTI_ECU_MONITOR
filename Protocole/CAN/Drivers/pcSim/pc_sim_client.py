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
                data, _ = sock.recvfrom(4096)
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

    def inject_can(self, node: int, can_id: int, payload: Iterable[int]) -> str:
        data: List[int] = [int(v) & 0xFF for v in payload]
        if len(data) > 8:
            raise ValueError("payload max length is 8")
        bytes_str = " ".join(str(v) for v in data)
        return self._send(f"INJECT_CAN {node} {can_id} {len(data)} {bytes_str}")

    def get_can_tx_count(self) -> int:
        rsp = self._send("GET_CAN_TX_COUNT")
        return int(self._parse_key_value(rsp, "COUNT"), 0)

    def clear_can_tx(self) -> int:
        rsp = self._send("CLEAR_CAN_TX")
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
