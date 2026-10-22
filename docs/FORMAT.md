# Session format, version 1

The recorder writes `color.rgb` as tightly packed RGB888 frames in row-major order and `depth.u16le` as tightly packed little-endian unsigned 16-bit depth frames. The requested OpenNI pixel format is DEPTH_1_MM. Confirm actual depth scale for your device/runtime before interpreting measurements.

There are no per-frame binary headers. Frame offset is index × width × height × bytes-per-pixel. The dimensions and encoding live in `metadata.json`; color and depth dimensions may differ. Files are uncompressed. Zero depth is treated as invalid by the preview statistics.

`timestamps.csv` has one row for each successfully written pair:

- `frame_index`: zero-based pair index.
- `host_monotonic_ns`, `host_epoch_ns`: host clocks sampled after the two reads.
- `color_frame_index`, `depth_frame_index`: sensor frame IDs.
- `color_sensor_timestamp_us`, `depth_sensor_timestamp_us`: timestamps reported by OpenNI.
- Color/depth width and height.

`metadata.json` includes the requested configuration, device information, stream format, registration outcome, and sync-request outcome. A failed registration or sync request is recorded rather than represented as success.

`summary.json` records written pair count, rejected frame count, elapsed seconds and approximate FPS after normal completion. An exception or abrupt process/power interruption can leave an incomplete session or no summary. Validate byte sizes against the timestamp rows before downstream use.

The synthetic example intentionally uses the same file contract and adds a `synthetic: true` label. Synthetic timestamps and dimensions are test data, not device measurements.
