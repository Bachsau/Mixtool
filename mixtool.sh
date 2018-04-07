#!/bin/sh
trap false INT
cd "$(dirname "$0")/src"
export 'LC_ALL'='en_US.utf8'
export 'G_SLICE'='always-malloc'
do_quit=''
while test -z "$do_quit"
do
	clear
	printf 'Launching Mixtool...\n' >&2
	python3 -BEs __main__.py "$@"
	printf 'Mixtool has quit with \e[1mexit code %b\e[0m.\n' $? >&2
	read -rn 1 -p '=> Press return to restart or any other key to exit.' do_quit
done
