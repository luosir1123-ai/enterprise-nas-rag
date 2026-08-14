#!/bin/bash
set -euo pipefail

NAS_IP="192.0.2.90"
NFS_EXPORT="/volume1/LE TOUCH SHR"
MOUNT_DIR="/Users/Shared/nas/LE_TOUCH_SHR"

/bin/mkdir -p "$MOUNT_DIR"
if /sbin/mount | /usr/bin/grep -Fq "on $MOUNT_DIR (nfs, read-only)"; then
  exit 0
fi

/sbin/mount_nfs -o vers=3,resvport,ro "$NAS_IP:$NFS_EXPORT" "$MOUNT_DIR"
