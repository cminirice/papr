#!/bin/sh
# Server-owned paths in a private temporary directory; never supplied by HTTP input.
set -eu
: "${PAPR_BROWSER_EXECUTABLE:?}"
: "${PAPR_BROWSER_PID_FILE:?}"
printf '%s\n' "$$" > "$PAPR_BROWSER_PID_FILE"
exec "$PAPR_BROWSER_EXECUTABLE" "$@"
