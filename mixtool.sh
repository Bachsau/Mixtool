#!/bin/sh
trap false INT
export LC_ALL='en_US.UTF-8'
export G_SLICE='debug-blocks'
appdir="$(dirname "$(realpath "$0")")"
printf 'Launching Mixtool\u2026 %s\n' "$(date '+%F %R %Z')" >>"$appdir/output.log"
python3 -BEsu "$appdir/src/__main__.py" "$@" &>>"$appdir/output.log"
printf 'Mixtool has quit with EXIT CODE %u.\n\n' $? >>"$appdir/output.log"
