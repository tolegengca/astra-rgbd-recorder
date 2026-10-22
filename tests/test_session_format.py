"""Camera-free checks of the public binary contract and preview CLI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]

def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

preview = load_script("export_preview")
example = load_script("make_example_session")

def test_rgb_frame_addressing(tmp_path):
    first = np.full((3, 4, 3), 17, np.uint8)
    second = np.full((3, 4, 3), 213, np.uint8)
    p = tmp_path / "color.rgb"
    p.write_bytes(first.tobytes() + second.tobytes())
    assert np.array_equal(preview.read_color_frame(p, 1, 4, 3), second)

def test_depth_is_little_endian_and_frame_indexed(tmp_path):
    p = tmp_path / "depth.u16le"
    p.write_bytes(bytes([1, 0, 0, 1, 255, 0, 255, 255]))
    assert preview.read_depth_frame(p, 0, 2, 1).tolist() == [[1, 256]]
    assert preview.read_depth_frame(p, 1, 2, 1).tolist() == [[255, 65535]]

@pytest.mark.parametrize("reader,filename", [(preview.read_color_frame, "color.rgb"), (preview.read_depth_frame, "depth.u16le")])
def test_incomplete_frames_fail(tmp_path, reader, filename):
    p = tmp_path / filename
    p.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="incomplete"):
        reader(p, 0, 4, 3)

def test_synthetic_session_exports_lossless_depth(tmp_path):
    session = example.make_session(tmp_path / "synthetic")
    subprocess.run([sys.executable, str(ROOT / "scripts/export_preview.py"), str(session), "--frame", "1"], check=True, capture_output=True)
    metadata = json.loads((session / "metadata.json").read_text())
    assert metadata["synthetic"] is True
    assert preview.count_rows(session / "timestamps.csv") == 3
    assert (session / "color.rgb").stat().st_size == 3 * 64 * 48 * 3
    assert (session / "depth.u16le").stat().st_size == 3 * 64 * 48 * 2
    raw = preview.read_depth_frame(session / "depth.u16le", 1, 64, 48)
    png = cv2.imread(str(session / "preview/depth_000001.u16.png"), cv2.IMREAD_UNCHANGED)
    assert png.dtype == np.uint16
    assert np.array_equal(png, raw)
    assert (session / "preview/color_000001.png").is_file()
    assert (session / "preview/depth_000001.png").is_file()

def test_out_of_range_preview_fails(tmp_path):
    session = example.make_session(tmp_path / "synthetic")
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/export_preview.py"), str(session), "--frame", "3"], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "Frame index must be between" in proc.stderr
