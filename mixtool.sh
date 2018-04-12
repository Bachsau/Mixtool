#!/bin/sh
trap false INT
export 'LC_ALL'='en_US.UTF-8'
export 'G_SLICE'='debug-blocks'
do_quit=''
while test -z "$do_quit"
do
	printf '\n\n\n\n'
	clear
	printf 'Launching Mixtool...\n' >&2
	python3 -BEs "$(dirname "$0")/src/__main__.py" "$@"
	printf 'Mixtool has quit with \e[1mexit code %b\e[0m.\n' $? >&2
	read -rn 1 -p '=> Press return to restart or any other key to exit.' do_quit
	printf '\n'
done
