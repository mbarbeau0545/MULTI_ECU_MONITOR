import argparse
import signal
import time
from pathlib import Path

from app.can_broker import PcSimCanBrokerService
from app.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=r"Doc\ConfigPrj\ecus_config.json")
    args = parser.parse_args()

    cfg = load_config(Path(args.config).resolve())
    broker = PcSimCanBrokerService(cfg)
    if not broker.is_enabled:
        print("[INFO] CAN broker disabled by config or not enough PCSIM ECUs")
        return 0

    stop = {"v": False}

    def _sig_handler(_sig, _frm):
        stop["v"] = True

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    broker.start()
    try:
        while not stop["v"]:
            time.sleep(1.0)
            st = broker.get_stats()
            print(
                "[BROKER] "
                f"rx={st['rx_frames']} routed={st['routed_frames']} "
                f"inj={st['injected_frames']} drop={st['dropped_frames']} "
                f"cycle={st['last_cycle_ms']}ms err={st['cycle_errors']}"
            )
    finally:
        broker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
