import re
from pathlib import Path
from typing import Dict, List


def _extract_enum_blocks(content: str) -> List[str]:
    return re.findall(r"typedef\s+enum\s*\{(.*?)\}\s*\w+\s*;", content, flags=re.S)


def _strip_c_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*?$", "", text, flags=re.M)
    return text


def _split_enum_entries(block: str) -> List[str]:
    clean = _strip_c_comments(block)
    return [entry.strip() for entry in clean.split(",") if entry.strip()]


def _parse_int_literal(expr: str) -> int:
    token = expr.strip().strip("()")
    token = re.sub(r"[uUlL]+$", "", token)
    return int(token, 0)


def _count_from_enum_nb(content: str, nb_token: str) -> int:
    for block in _extract_enum_blocks(content):
        entries = _split_enum_entries(block)
        if not entries:
            continue

        current = -1
        for entry in entries:
            if "=" in entry:
                name, value_expr = entry.split("=", 1)
                name = name.strip()
                value_expr = value_expr.strip()
                try:
                    current = _parse_int_literal(value_expr)
                except Exception:
                    # If expression is not a plain integer literal, keep monotonic order.
                    current += 1
            else:
                name = entry.strip()
                current += 1

            if name == nb_token:
                return max(0, current)
    return 0


def _count_prefixed_items(content: str, prefix: str) -> int:
    matches = re.findall(rf"\b{re.escape(prefix)}(\d+)\b", content)
    if not matches:
        return 0
    return len({int(m) for m in matches})


def parse_fmkio_counts(path: Path) -> Dict[str, int]:
    counts = {"ana": 0, "pwm": 0, "in_dig": 0, "out_dig": 0, "in_freq": 0, "enc": 0}
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return counts

    counts["ana"] = _count_from_enum_nb(content, "FMKIO_INPUT_SIGANA_NB")
    counts["pwm"] = _count_from_enum_nb(content, "FMKIO_OUTPUT_SIGPWM_NB")
    counts["in_dig"] = _count_from_enum_nb(content, "FMKIO_INPUT_SIGDIG_NB")
    counts["out_dig"] = _count_from_enum_nb(content, "FMKIO_OUTPUT_SIGDIG_NB")
    counts["in_freq"] = _count_from_enum_nb(content, "FMKIO_INPUT_SIGFREQ_NB")
    counts["enc"] = _count_from_enum_nb(content, "FMKIO_INPUT_ENCODER_NB")

    if counts["ana"] == 0:
        counts["ana"] = _count_prefixed_items(content, "FMKIO_INPUT_SIGANA_")
    if counts["pwm"] == 0:
        counts["pwm"] = _count_prefixed_items(content, "FMKIO_OUTPUT_SIGPWM_")
    if counts["in_dig"] == 0:
        counts["in_dig"] = _count_prefixed_items(content, "FMKIO_INPUT_SIGDIG_")
    if counts["out_dig"] == 0:
        counts["out_dig"] = _count_prefixed_items(content, "FMKIO_OUTPUT_SIGDIG_")
    if counts["in_freq"] == 0:
        counts["in_freq"] = _count_prefixed_items(content, "FMKIO_INPUT_SIGFREQ_")
    if counts["enc"] == 0:
        counts["enc"] = _count_prefixed_items(content, "FMKIO_INPUT_ENCODER_")

    return counts
