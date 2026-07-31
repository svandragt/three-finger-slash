#!/bin/sh
# Wrapper for keyboard-shortcut launchers that don't inherit a full desktop env.
export DISPLAY="${DISPLAY:-:0}"
{
	echo "$(date -Iseconds) triggered"
	/home/sander/dev/lua/three-finger-slash/linux/three_finger_slash.py
	echo "$(date -Iseconds) exit=$?"
} >>/tmp/tfs.log 2>&1
