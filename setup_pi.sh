#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cat <<'EOF'

Python dependencies installed.

Next manual steps:
1. Install Orbbec/OpenNI2 runtime for your Raspberry Pi OS architecture.
2. Copy the udev rule:
   sudo cp udev/56-orbbec.rules /etc/udev/rules.d/
   sudo udevadm control --reload-rules
   sudo udevadm trigger
3. Test camera visibility:
   python astra_record.py --duration-sec 3 --out recordings_test

If OpenNI2 is installed outside the loader path, pass:
   --openni2-lib /path/to/OpenNI2/Redist

EOF
