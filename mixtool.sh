#!/bin/sh
trap false INT
appdir=$(dirname "$(realpath "$0")")
export LC_ALL=en_US.UTF-8
export G_SLICE=debug-blocks
#export G_RESOURCE_OVERLAYS=/com/bachsau/mixtool=$appdir/src/res
printf '\n[%u] Launching Mixtool... %s\n' $$ "$(date '+%F %T %Z')" >>"$appdir/output.log"
python3 -BEsu "$appdir/src/__main__.py" "$@" >>"$appdir/output.log" 2>&1
status=$?
printf '[%u] Mixtool has quit with EXIT CODE %u.\n\n' $$ $status >>"$appdir/output.log"
unset LC_ALL G_SLICE
if [ $status -ne 0 ]; then
	if [ -n "$(command -v xdg-open)" ]; then
		exec xdg-open "$appdir/output.log"
	elif [ -n "$(command -v open)" ]; then
		exec open "$appdir/output.log"
	fi
fi
