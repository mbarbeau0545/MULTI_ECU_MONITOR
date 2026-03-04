from typing import Any, Dict, List, Optional

from .script_runtime_api import (
    get_signal,
    send_symbol_msg,
    sleep_ms,
    stop_requested,
)

HC_CMD_SYMBOL = "LGC_HC_CMD_POSITION"


def send_hc_joint(
    alpha_b_mrad: float,
    alpha_c_mrad: float,
    knife_rpm: float = 20.0,
    cntr_knife_rpm: float = 20.0,
    pos_id: int = 1,
    node: Optional[int] = None,
) -> None:
    send_symbol_msg(
        HC_CMD_SYMBOL,
        {
            "LGC_HC_CMD_KNIFE_POS_X_ALPH_A": alpha_b_mrad,
            "LGC_HC_CMD_KNIFE_POS_Y_ALPH_B": alpha_c_mrad,
            "LGC_HC_CMD_KNF_POS_SPD_RPM": knife_rpm,
            "LGC_HC_CMD_CNTR_KNF_POS_SPD_RPM": cntr_knife_rpm,
            "LGC_HC_CMD_KNIFE_TYPE_ID": 1,
            "LGC_HC_CMD_KNIFE_POS_ID": pos_id,
        },
        node=node,
    )


def send_hc_cartesian(
    x_mm: float,
    y_mm: float,
    knife_rpm: float = 20.0,
    cntr_knife_rpm: float = 20.0,
    pos_id: int = 1,
    node: Optional[int] = None,
) -> None:
    send_symbol_msg(
        HC_CMD_SYMBOL,
        {
            "LGC_HC_CMD_KNIFE_POS_X_ALPH_A": x_mm,
            "LGC_HC_CMD_KNIFE_POS_Y_ALPH_B": y_mm,
            "LGC_HC_CMD_KNF_POS_SPD_RPM": knife_rpm,
            "LGC_HC_CMD_CNTR_KNF_POS_SPD_RPM": cntr_knife_rpm,
            "LGC_HC_CMD_KNIFE_TYPE_ID": 0,
            "LGC_HC_CMD_KNIFE_POS_ID": pos_id,
        },
        node=node,
    )


def send_hc_trajectory_joint(
    points: List[Any],
    dt_ms: int = 10,
    start_pos_id: int = 1,
    knife_rpm: float = 20.0,
    cntr_knife_rpm: float = 20.0,
    node: Optional[int] = None,
) -> None:
    pos_id = int(start_pos_id) & 0xFFFF
    delay = max(0, int(dt_ms))
    for point in points:
        if stop_requested():
            break
        if isinstance(point, dict):
            a = float(point.get("alpha_b", point.get("a", 0.0)))
            c = float(point.get("alpha_c", point.get("c", 0.0)))
            spd_k = float(point.get("knife_rpm", knife_rpm))
            spd_ck = float(point.get("cntr_knife_rpm", cntr_knife_rpm))
            pid = int(point.get("pos_id", pos_id)) & 0xFFFF
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            a = float(point[0])
            c = float(point[1])
            spd_k = float(point[2]) if len(point) > 2 else knife_rpm
            spd_ck = float(point[3]) if len(point) > 3 else cntr_knife_rpm
            pid = int(point[4]) & 0xFFFF if len(point) > 4 else pos_id
        else:
            continue

        send_hc_joint(a, c, spd_k, spd_ck, pid, node=node)
        pos_id = (pid + 1) & 0xFFFF
        sleep_ms(delay)


def send_hc_trajectory_cartesian(
    points: List[Any],
    dt_ms: int = 10,
    start_pos_id: int = 1,
    knife_rpm: float = 20.0,
    cntr_knife_rpm: float = 20.0,
    node: Optional[int] = None,
) -> None:
    pos_id = int(start_pos_id) & 0xFFFF
    delay = max(0, int(dt_ms))
    for point in points:
        if stop_requested():
            break
        if isinstance(point, dict):
            x = float(point.get("x", 0.0))
            y = float(point.get("y", 0.0))
            spd_k = float(point.get("knife_rpm", knife_rpm))
            spd_ck = float(point.get("cntr_knife_rpm", cntr_knife_rpm))
            pid = int(point.get("pos_id", pos_id)) & 0xFFFF
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            x = float(point[0])
            y = float(point[1])
            spd_k = float(point[2]) if len(point) > 2 else knife_rpm
            spd_ck = float(point[3]) if len(point) > 3 else cntr_knife_rpm
            pid = int(point[4]) & 0xFFFF if len(point) > 4 else pos_id
        else:
            continue

        send_hc_cartesian(x, y, spd_k, spd_ck, pid, node=node)
        pos_id = (pid + 1) & 0xFFFF
        sleep_ms(delay)


def get_hc_feedback(timeout_ms: int = 0) -> Dict[str, Any]:
    return {
        "x_mm": get_signal("LGC_HC_FB_AXE_X_POS", timeout_ms=timeout_ms),
        "y_mm": get_signal("LGC_HC_FB_AXE_Y_POS", timeout_ms=timeout_ms),
        "alpha_b_mrad": get_signal("LGC_HC_FB_ALPHA_B_ANGLE", timeout_ms=timeout_ms),
        "alpha_c_mrad": get_signal("LGC_HC_FB_ALPHA_C_ANGLE", timeout_ms=timeout_ms),
    }


__all__ = [
    "HC_CMD_SYMBOL",
    "send_hc_joint",
    "send_hc_cartesian",
    "send_hc_trajectory_joint",
    "send_hc_trajectory_cartesian",
    "get_hc_feedback",
]
