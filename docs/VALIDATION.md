# Validation record

Publication preparation: 2026-10-22, Python 3.12 on macOS arm64.

Six camera-free tests passed:

1. RGB random-access addressing returns the selected frame.
2. Depth decoding respects little-endian uint16 values and frame offsets.
3. An incomplete RGB frame is rejected.
4. An incomplete depth frame is rejected.
5. A synthetic session exports preview images and preserves raw depth values in 16-bit PNG.
6. The preview CLI rejects an out-of-range frame.

These tests use synthetic data. The recorder CLI `--help` ran successfully with the primesense Python package installed, and the synthetic-session/preview commands completed. No Astra camera, OpenNI2 native runtime, Raspberry Pi, systemd service, hardware synchronization, or sustained storage throughput was tested in this preparation.

## Hardware acceptance checklist

- Record OS/CPU architecture, camera model, OpenNI2/runtime version and supported modes.
- Capture a short session and verify byte counts against CSV rows and stream dimensions.
- Inspect RGB/depth previews and invalid-depth behavior.
- Analyze color/depth sensor timestamp deltas and sensor frame-index gaps.
- Perform a longer storage test; report actual FPS, disk usage, rejected frames and temperature.
- Test Ctrl+C, SIGTERM, insufficient disk space and restart behavior on the intended deployment.

A sync request accepted by the API is not equivalent to proven synchronization. `bad_frames` is not a complete dropped-frame metric. No hardware performance claims are made by this repository.

## Publication environment

- numpy 2.5.4
- scipy 1.18.1
- opencv-python-headless 4.14.0.94
- pytest 9.1.1
