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
		IFS=':'
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
#export G_SLICE=debug-blocks
export G_ENABLE_DIAGNOSTIC=1
export GTK_THEME=Adwaita
export G_RESOURCE_OVERLAYS="/com/bachsau/mixtool=$appdir/src/res"
mkdir -p "$appdir/logs"
olog=$appdir/logs/output.log
elog=$appdir/logs/$(date '+errors_%y%m%d-%H%M%S.log')
date '+Launching Mixtool... %F %T %Z%n' >"$elog"
python3 -BEsuWd "$appdir/src/__main__.py" "$@" >>"$olog" 2>>"$elog"
status=$?
printf '\nMixtool has quit with EXIT CODE %u.\n\n' $status >>"$elog"
unset LC_ALL G_SLICE GTK_THEME
if [ $status -ne 0 ]; then
	if [ -n "$(command -v xdg-open)" ]; then
		xdg-open "$elog" &
	elif [ -n "$(command -v open)" ]; then
		open "$elog" &
	fi
fi
