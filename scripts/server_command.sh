#!/bin/sh
set -eu
: "${ATLAS_SERVER_HOST:?Set ATLAS_SERVER_HOST in your environment}"
exec ssh -o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4 "$ATLAS_SERVER_HOST" "$@"
