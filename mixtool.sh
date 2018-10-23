#!/bin/sh

# This is a debug launcher!
# A modified version named "mixtool" should be placed in /usr/bin,
# with the scripts and resources located in /usr/lib/mixtool
# on distribution.
#
# Please do not use python's site-packages directory unless
# you're packaging for PyPI.

find_path() {
	fullpath=$(echo $1 |grep /)
	if [ -z "$fullpath" ]; then
		oIFS=$IFS
		IFS=:
		for path in $PATH; do
			if [ -x "$path/$1" ]; then
				if [ -z "$path" ]; then
					path="."
				fi
				fullpath=$path/$1
				break
			fi
		done
		IFS=$oIFS
	fi
	if [ -z "$fullpath" ]; then
		fullpath=$1
	fi

	if [ -L "$fullpath" ]; then
		fullpath=$(ls -l "$fullpath" |sed -e 's/.* -> //' |sed -e 's/\*//')
	fi
	dirname "$fullpath"
}

trap false INT
appdir=$(find_path "$0")
export LC_ALL=en_US.UTF-8
export G_SLICE=debug-blocks
export GTK_THEME=Adwaita
#export G_RESOURCE_OVERLAYS=/com/bachsau/mixtool=$appdir/src/res
printf '\n[%u] Launching Mixtool... %s\n' $$ "$(date '+%F %T %Z')" >>"$appdir/output.log"
python3 -BEsuWd "$appdir/src/__main__.py" "$@" >>"$appdir/output.log" 2>&1
status=$?
printf '[%u] Mixtool has quit with EXIT CODE %u.\n\n' $$ $status >>"$appdir/output.log"
unset LC_ALL G_SLICE GTK_THEME
if [ $status -ne 0 ]; then
	if [ -n "$(command -v xdg-open)" ]; then
		exec xdg-open "$appdir/output.log"
	elif [ -n "$(command -v open)" ]; then
		exec open "$appdir/output.log"
	fi
fi
