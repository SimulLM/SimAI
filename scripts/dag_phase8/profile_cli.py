"""Measure an isolated original CLI process, including startup and output export."""
import argparse
import json
from pathlib import Path
import runpy
import sys
import threading
import time

import psutil


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--performance-output", required=True)
    args, remaining = parser.parse_known_args()
    sys.argv = ["vidur.main", *remaining]
    process = psutil.Process()
    stop = threading.Event()
    peaks = []
    def sample():
        while True:
            info = process.memory_info()
            peaks.append(max(info.rss, getattr(info, "peak_wset", 0)))
            if stop.wait(.05):
                return
    worker = threading.Thread(target=sample, daemon=True)
    started = time.perf_counter()
    worker.start()
    error = None
    try:
        runpy.run_module("vidur.main", run_name="__main__")
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stop.set()
        worker.join()
        Path(args.performance_output).write_text(json.dumps(dict(
            wall_time_s=time.perf_counter() - started, peak_rss_bytes=max(peaks),
            memory_measurement="process RSS sampled every 50ms, includes Windows peak_wset when available",
            memory_samples=len(peaks), includes="CLI import, predictor, simulation, metrics and exports",
            error=error), indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
