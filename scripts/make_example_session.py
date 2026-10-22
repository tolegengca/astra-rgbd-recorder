#!/usr/bin/env python3
"""Generate a tiny synthetic session using the recorder's binary contract."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import numpy as np


def make_session(path: Path, width: int = 64, height: int = 48, frames: int = 3) -> Path:
    path.mkdir(parents=True, exist_ok=False)
    metadata = {
        "format_version": 1,
        "synthetic": True,
        "device": {"name": "Synthetic test pattern — not a camera capture"},
        "streams": {
            "color": {"width": width, "height": height, "fps": 30,
                      "encoding": "RGB888", "file": "color.rgb"},
            "depth": {"width": width, "height": height, "fps": 30,
                      "encoding": "uint16_le_mm", "file": "depth.u16le"},
        },
        "registration": "synthetic_not_applicable",
        "depth_color_sync": "synthetic_not_applicable",
    }
    (path / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    y, x = np.indices((height, width))
    fields = ["frame_index", "host_monotonic_ns", "host_epoch_ns",
              "color_frame_index", "depth_frame_index", "color_sensor_timestamp_us",
              "depth_sensor_timestamp_us", "color_width", "color_height", "depth_width", "depth_height"]
    with (path / "timestamps.csv").open("w", newline="") as ts, (path / "color.rgb").open("wb") as cf, (path / "depth.u16le").open("wb") as df:
        writer = csv.DictWriter(ts, fieldnames=fields)
        writer.writeheader()
        for i in range(frames):
            color = np.stack(((x * 4 + i * 30) % 256, (y * 5) % 256, np.full_like(x, 100)), axis=-1).astype(np.uint8)
            depth = (500 + x * 10 + y * 5 + i).astype("<u2")
            depth[0, 0] = 0
            cf.write(color.tobytes())
            df.write(depth.tobytes())
            writer.writerow(dict(zip(fields, [i, i * 33_333_333, i * 33_333_333,
                                               i, i, i * 33_333, i * 33_333,
                                               width, height, width, height])))
    (path / "summary.json").write_text(json.dumps({"synthetic": True, "frames": frames, "bad_frames": 0}, indent=2) + "\n")
    (path / "notes.txt").write_text("Synthetic format fixture. No camera or real person was recorded.\n")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("recordings_example/synthetic"))
    args = parser.parse_args()
    print(make_session(args.out))
