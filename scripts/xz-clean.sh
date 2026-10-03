# Sourced by scripts/ci.sh and the probes that keep compressed logs.
#
# The style gate (Q-12, scripts/check-style.sh) looks for the byte sequences
# of an em or en dash in every file of the working tree, compressed logs
# included. Compressed data holds one of those three-byte sequences by
# chance about once in every 8 MB, so a kept log can fail the gate without
# containing a dash. xz_clean compresses with the first preset whose output
# holds neither sequence.

# Compress `src` with xz into `dest`, keeping `src`.
xz_clean() { # src dest
	local preset
	for preset in -9 -9e -8 -8e -7 -7e -6; do
		xz "$preset" -T1 -c "$1" > "$2" || return 1
		LC_ALL=C grep -q $'\xe2\x80\x94\|\xe2\x80\x93' "$2" || return 0
	done
	printf 'xz_clean: every preset left dash bytes in %s\n' "$2" >&2
	return 1
}

# Compress each file in place, as `xz` does: `f` becomes `f.xz`.
xz_clean_in_place() { # file...
	local f
	for f in "$@"; do
		[ -f "$f" ] || continue
		xz_clean "$f" "$f.xz" && rm -f "$f"
	done
}
