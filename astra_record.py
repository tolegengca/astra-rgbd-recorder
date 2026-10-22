#!/usr/bin/env python3
"""
Minimal RGB+Depth recorder for Orbbec Astra S / OpenNI2 cameras.

Output format is intentionally boring and robust for a Raspberry Pi:

session/
  metadata.json
  timestamps.csv
  color.rgb        contiguous RGB888 frames
  depth.u16le      contiguous uint16 little-endian depth frames, usually in mm

The raw binary files avoid per-frame PNG/JPEG CPU overhead and preserve the
original stream values. Use scripts/export_preview.py to inspect a session.
"""

from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from primesense import openni2
from primesense import _openni2 as c_api


PIXEL_FORMAT_DEPTH_1_MM = 100
PIXEL_FORMAT_RGB888 = 200


@dataclass(frozen=True)
class StreamConfig:
    width: int
    height: int
    fps: int


@dataclass(frozen=True)
class RecorderConfig:
    color: StreamConfig
    depth: StreamConfig
    openni2_lib: str | None
    device_uri: str | None
    duration_sec: float | None
    out_dir: str
    registration: bool
    depth_color_sync: bool
    flush_every: int


class StopFlag:
    def __init__(self) -> None:
        self.stop = False

    def request_stop(self, _signum: int, _frame: Any) -> None:
        self.stop = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record synchronized RGB+Depth streams from an Orbbec Astra S via OpenNI2."
    )
    parser.add_argument("--out", default="recordings", help="Base directory for sessions.")
    parser.add_argument("--session-name", default=None, help="Optional session folder name.")
    parser.add_argument("--openni2-lib", default=None, help="Path containing OpenNI2 shared libraries.")
    parser.add_argument("--device-uri", default=None, help="OpenNI2 device URI; omitted means any device.")
    parser.add_argument("--duration-sec", type=float, default=None, help="Stop after N seconds.")
    parser.add_argument("--duration-min", type=float, default=None, help="Stop after N minutes.")
    parser.add_argument("--color-width", type=int, default=640)
    parser.add_argument("--color-height", type=int, default=480)
    parser.add_argument("--depth-width", type=int, default=640)
    parser.add_argument("--depth-height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--no-registration", action="store_true", help="Do not register depth to color.")
    parser.add_argument("--no-depth-color-sync", action="store_true", help="Do not ask device for HW sync.")
    parser.add_argument("--flush-every", type=int, default=30, help="Flush files every N frame pairs.")
    return parser.parse_args()


def init_openni(openni2_lib: str | None) -> None:
    try:
        if openni2_lib:
            openni2.initialize(openni2_lib)
        else:
            openni2.initialize()
    except Exception as exc:  # pragma: no cover - depends on target Pi
        hint = (
            "OpenNI2 did not initialize. Install Orbbec/OpenNI2 runtime and pass "
            "--openni2-lib /path/to/OpenNI2/Redist if it is not in the default loader path."
        )
        raise RuntimeError(hint) from exc


def open_device(device_uri: str | None) -> openni2.Device:
    if device_uri:
        return openni2.Device.open_file(device_uri) if Path(device_uri).is_file() else openni2.Device.open_uri(device_uri)
    return openni2.Device.open_any()


def set_video_mode(stream: openni2.VideoStream, config: StreamConfig, pixel_format: int) -> None:
    mode = c_api.OniVideoMode(
        pixelFormat=pixel_format,
        resolutionX=config.width,
        resolutionY=config.height,
        fps=config.fps,
    )
    stream.set_video_mode(mode)


def maybe_enable_registration(device: openni2.Device, enabled: bool) -> str:
    if not enabled:
        return "disabled_by_user"

    try:
        device.set_image_registration_mode(openni2.IMAGE_REGISTRATION_DEPTH_TO_COLOR)
        return "depth_to_color"
    except Exception as exc:  # pragma: no cover - device-dependent
        return f"not_enabled:{type(exc).__name__}:{exc}"


def maybe_enable_depth_color_sync(device: openni2.Device, enabled: bool) -> str:
    if not enabled:
        return "disabled_by_user"

    try:
        device.set_depth_color_sync_enabled(True)
        return "enabled"
    except Exception as exc:  # pragma: no cover - device-dependent
        return f"not_enabled:{type(exc).__name__}:{exc}"


def session_dir(base_dir: str, session_name: str | None) -> Path:
    name = session_name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(base_dir).expanduser().resolve() / name
    path.mkdir(parents=True, exist_ok=False)
    (path / "notes.txt").write_text(
        "Record capture conditions: operator, camera angle, Pi model, power, lighting.\n",
        encoding="utf-8",
    )
    return path


def frame_to_color_array(frame: openni2.VideoFrame) -> np.ndarray:
    data = frame.get_buffer_as_uint8()
    array = np.frombuffer(data, dtype=np.uint8)
    return array.reshape((frame.height, frame.width, 3))


def frame_to_depth_array(frame: openni2.VideoFrame) -> np.ndarray:
    data = frame.get_buffer_as_uint16()
    array = np.frombuffer(data, dtype=np.uint16)
    return array.reshape((frame.height, frame.width))


def metadata_for(
    config: RecorderConfig,
    device: openni2.Device,
    session: Path,
    registration_status: str,
    sync_status: str,
) -> dict[str, Any]:
    info = device.get_device_info()
    return {
        "format_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "session_dir": str(session),
        "device": {
            "name": getattr(info, "name", None),
            "uri": getattr(info, "uri", None),
            "vendor": getattr(info, "vendor", None),
            "usb_product_id": getattr(info, "usbProductId", None),
            "usb_vendor_id": getattr(info, "usbVendorId", None),
        },
        "streams": {
            "color": {**asdict(config.color), "encoding": "RGB888", "file": "color.rgb"},
            "depth": {**asdict(config.depth), "encoding": "uint16_le_mm", "file": "depth.u16le"},
        },
        "registration": registration_status,
        "depth_color_sync": sync_status,
        "notes": {
            "camera": "Orbbec Astra S",
            "mount_angle_target_deg": "35-45 down",
            "recommended_first_test": "10-15 minutes, hands and objects at normal manipulation distance",
        },
    }


def record(config: RecorderConfig, session: Path) -> int:
    init_openni(config.openni2_lib)
    device = open_device(config.device_uri)

    depth_stream = device.create_depth_stream()
    color_stream = device.create_color_stream()

    set_video_mode(depth_stream, config.depth, PIXEL_FORMAT_DEPTH_1_MM)
    set_video_mode(color_stream, config.color, PIXEL_FORMAT_RGB888)

    sync_status = maybe_enable_depth_color_sync(device, config.depth_color_sync)
    registration_status = maybe_enable_registration(device, config.registration)

    metadata = metadata_for(config, device, session, registration_status, sync_status)
    (session / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    stop_flag = StopFlag()
    signal.signal(signal.SIGINT, stop_flag.request_stop)
    signal.signal(signal.SIGTERM, stop_flag.request_stop)

    timestamps_path = session / "timestamps.csv"
    color_path = session / "color.rgb"
    depth_path = session / "depth.u16le"

    frame_count = 0
    dropped_or_bad = 0
    started = time.monotonic()

    with timestamps_path.open("w", newline="", encoding="utf-8") as timestamps_file, color_path.open("wb") as color_file, depth_path.open("wb") as depth_file:
        writer = csv.DictWriter(
            timestamps_file,
            fieldnames=[
                "frame_index",
                "host_monotonic_ns",
                "host_epoch_ns",
                "color_frame_index",
                "depth_frame_index",
                "color_sensor_timestamp_us",
                "depth_sensor_timestamp_us",
                "color_width",
                "color_height",
                "depth_width",
                "depth_height",
            ],
        )
        writer.writeheader()

        depth_stream.start()
        color_stream.start()
        try:
            while not stop_flag.stop:
                if config.duration_sec is not None and time.monotonic() - started >= config.duration_sec:
                    break

                depth_frame = depth_stream.read_frame()
                color_frame = color_stream.read_frame()
                host_monotonic_ns = time.monotonic_ns()
                host_epoch_ns = time.time_ns()

                if depth_frame is None or color_frame is None:
                    dropped_or_bad += 1
                    continue

                try:
                    depth = frame_to_depth_array(depth_frame)
                    color = frame_to_color_array(color_frame)
                except ValueError:
                    dropped_or_bad += 1
                    continue

                if depth.shape != (config.depth.height, config.depth.width):
                    dropped_or_bad += 1
                    continue
                if color.shape != (config.color.height, config.color.width, 3):
                    dropped_or_bad += 1
                    continue

                color_file.write(color.tobytes(order="C"))
                depth_file.write(depth.astype("<u2", copy=False).tobytes(order="C"))
                writer.writerow(
                    {
                        "frame_index": frame_count,
                        "host_monotonic_ns": host_monotonic_ns,
                        "host_epoch_ns": host_epoch_ns,
                        "color_frame_index": color_frame.frameIndex,
                        "depth_frame_index": depth_frame.frameIndex,
                        "color_sensor_timestamp_us": color_frame.timestamp,
                        "depth_sensor_timestamp_us": depth_frame.timestamp,
                        "color_width": color_frame.width,
                        "color_height": color_frame.height,
                        "depth_width": depth_frame.width,
                        "depth_height": depth_frame.height,
                    }
                )

                frame_count += 1
                if frame_count % max(1, config.flush_every) == 0:
                    color_file.flush()
                    depth_file.flush()
                    timestamps_file.flush()
                    elapsed = max(time.monotonic() - started, 1e-6)
                    print(f"\rframes={frame_count} fps={frame_count / elapsed:.1f} bad={dropped_or_bad}", end="", flush=True)
        finally:
            print()
            color_stream.stop()
            depth_stream.stop()
            openni2.unload()

    summary = {
        "frames": frame_count,
        "bad_frames": dropped_or_bad,
        "elapsed_sec": time.monotonic() - started,
        "approx_fps": frame_count / max(time.monotonic() - started, 1e-6),
    }
    (session / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {frame_count} frame pairs to {session}")
    return 0 if frame_count > 0 else 2


def main() -> int:
    args = parse_args()
    duration_sec = args.duration_sec
    if args.duration_min is not None:
        duration_sec = args.duration_min * 60.0

    config = RecorderConfig(
        color=StreamConfig(args.color_width, args.color_height, args.fps),
        depth=StreamConfig(args.depth_width, args.depth_height, args.fps),
        openni2_lib=args.openni2_lib,
        device_uri=args.device_uri,
        duration_sec=duration_sec,
        out_dir=args.out,
        registration=not args.no_registration,
        depth_color_sync=not args.no_depth_color_sync,
        flush_every=args.flush_every,
    )
    try:
        session = session_dir(config.out_dir, args.session_name)
        return record(config, session)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
