#!/bin/sh
trap false INT
export LC_ALL='en_US.UTF-8'
export G_SLICE='debug-blocks'
appdir="$(dirname "$(realpath "$0")")"
printf 'Launching Mixtool... %s\n' "$(date '+%F %T %Z')" >>"$appdir/output.log"
python3 -BEsu "$appdir/src/__main__.py" "$@" >>"$appdir/output.log" 2>&1
printf 'Mixtool has quit with EXIT CODE %u.\n\n' $? >>"$appdir/output.log"
if [[ -n "$(command -v zenity)" && (-n "$(command -v xdg-open)" || -n "$(command -v open)") ]]
then
	zenity --question --no-wrap --no-markup --text 'Open "debug.log"?' --ok-label 'Yes' --cancel-label 'No' >'/dev/null' 2>&1
	if [[ $? -eq 0 ]]
	then
		unset LC_ALL G_SLICE
		if [[ -n "$(command -v xdg-open)" ]]
		then
			exec xdg-open "$appdir/output.log"
		else
			exec open "$appdir/output.log"
		fi
	fi
fi
