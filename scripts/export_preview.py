#!/usr/bin/env python3
"""
Export preview PNG files from an astra_record.py session.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export RGB and depth preview images from a recording session.")
    parser.add_argument("session", help="Path to a session folder.")
    parser.add_argument("--frame", type=int, default=0, help="Frame index to export.")
    parser.add_argument("--out", default=None, help="Output directory; default: session/preview.")
    parser.add_argument("--depth-max-mm", type=int, default=2500, help="Depth range upper bound for visualization.")
    return parser.parse_args()


def count_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as file:
        return max(0, sum(1 for _ in csv.DictReader(file)))


def read_color_frame(path: Path, index: int, width: int, height: int) -> np.ndarray:
    frame_size = width * height * 3
    with path.open("rb") as file:
        file.seek(index * frame_size)
        data = file.read(frame_size)
    if len(data) != frame_size:
        raise ValueError(f"Color frame {index} is incomplete.")
    return np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3))


def read_depth_frame(path: Path, index: int, width: int, height: int) -> np.ndarray:
    frame_size = width * height * 2
    with path.open("rb") as file:
        file.seek(index * frame_size)
        data = file.read(frame_size)
    if len(data) != frame_size:
        raise ValueError(f"Depth frame {index} is incomplete.")
    return np.frombuffer(data, dtype="<u2").reshape((height, width))


def depth_to_preview(depth: np.ndarray, depth_max_mm: int) -> np.ndarray:
    clipped = np.clip(depth, 0, depth_max_mm)
    normalized = (clipped.astype(np.float32) / float(depth_max_mm) * 255.0).astype(np.uint8)
    normalized[depth == 0] = 0
    return cv2.applyColorMap(normalized, cv2.COLORMAP_TURBO)


def main() -> int:
    args = parse_args()
    session = Path(args.session).expanduser().resolve()
    metadata = json.loads((session / "metadata.json").read_text(encoding="utf-8"))
    total_frames = count_rows(session / "timestamps.csv")
    if args.frame < 0 or args.frame >= total_frames:
        raise ValueError(f"Frame index must be between 0 and {total_frames - 1}.")

    color_info = metadata["streams"]["color"]
    depth_info = metadata["streams"]["depth"]
    color = read_color_frame(session / color_info["file"], args.frame, color_info["width"], color_info["height"])
    depth = read_depth_frame(session / depth_info["file"], args.frame, depth_info["width"], depth_info["height"])

    out_dir = Path(args.out).expanduser().resolve() if args.out else session / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    color_path = out_dir / f"color_{args.frame:06d}.png"
    depth_path = out_dir / f"depth_{args.frame:06d}.png"
    depth_raw_path = out_dir / f"depth_{args.frame:06d}.u16.png"

    cv2.imwrite(str(color_path), cv2.cvtColor(color, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(depth_path), depth_to_preview(depth, args.depth_max_mm))
    cv2.imwrite(str(depth_raw_path), depth)

    valid_depth = depth[depth > 0]
    if valid_depth.size:
        print(
            f"Exported frame {args.frame}: {color_path}, {depth_path}. "
            f"depth_mm min={int(valid_depth.min())} median={int(np.median(valid_depth))} max={int(valid_depth.max())}"
        )
    else:
        print(f"Exported frame {args.frame}: {color_path}, {depth_path}. No valid depth pixels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
