#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf abc > "$TMP/sample.txt"
EXPECTED='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
cc -std=c11 -Wall -Wextra -Werror -I"$ROOT/npcip_components/native/shared" "$ROOT/npcip_components/native/c/filehash.c" -o "$TMP/filehash"
g++ -std=c++17 -Wall -Wextra -Werror -I"$ROOT/npcip_components/native/shared" "$ROOT/npcip_components/native/cpp/filehash.cpp" -o "$TMP/filehash-cpp"
test "$("$TMP/filehash" "$TMP/sample.txt" | sed -n 's/^sha256=//p')" = "$EXPECTED"
test "$("$TMP/filehash-cpp" "$TMP/sample.txt" | sed -n 's/^sha256=//p')" = "$EXPECTED"
printf '{"action":"case.created"}\n{"action":"case.created"}\n' > "$TMP/audit.jsonl"
g++ -std=c++17 -Wall -Wextra -Werror "$ROOT/npcip_components/native/cpp/audit_analyzer.cpp" -o "$TMP/audit-analyzer"
"$TMP/audit-analyzer" "$TMP/audit.jsonl" | grep -q 'records_with_action=2'
echo 'PASS: C/C++ SHA-256 and C++ audit analyzer.'
