#!/usr/bin/env bash
set -euo pipefail

NAS_IP="${NAS_IP:-192.0.2.153}"
MOUNT_DIR="${MOUNT_DIR:-/Users/Shared/nas/LE_TOUCH_SHR}"
NFS_EXPORT="${NFS_EXPORT:-/volume1/LE TOUCH SHR}"

echo "== Mac mini network =="
networksetup -listallhardwareports || true
echo

echo "== Ethernet IP candidates =="
for dev in en0 en1 en2 en3; do
  ip="$(ipconfig getifaddr "$dev" 2>/dev/null || true)"
  if [[ -n "$ip" ]]; then
    echo "$dev: $ip"
  fi
done
echo

echo "== Ping NAS =="
ping -c 4 "$NAS_IP"
echo

echo "== NFS exports =="
showmount -e "$NAS_IP"
echo

echo "== Mount point =="
sudo mkdir -p "$MOUNT_DIR"
mount | grep "$MOUNT_DIR" || true
echo

echo "== Try readonly NFS mount =="
if mount | grep -q "on $MOUNT_DIR "; then
  echo "Already mounted: $MOUNT_DIR"
else
  sudo mount -t nfs -o vers=3,resvport,ro "${NAS_IP}:${NFS_EXPORT}" "$MOUNT_DIR"
fi
echo

echo "== List mounted root =="
ls -la "$MOUNT_DIR" | head -80
echo

echo "== Readonly write test, expected to fail =="
if touch "$MOUNT_DIR/.rag_write_test" 2>/tmp/rag_write_test.err; then
  rm -f "$MOUNT_DIR/.rag_write_test"
  echo "ERROR: mount is writable. Please change DSM NFS permission to readonly."
  exit 2
else
  cat /tmp/rag_write_test.err || true
  echo "OK: write test failed, mount is readonly."
fi
