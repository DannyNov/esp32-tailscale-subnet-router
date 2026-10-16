#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 - <<'PY'
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('patch','apply_patch.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
Path('tests/generated_snapshot_functions.c').write_text(m.FUNCTIONS,encoding='utf-8')
PY
for CC in gcc clang; do
    command -v "$CC"
    for MODE in normal sanitize; do
        EXTRA=""
        if [ "$MODE" = sanitize ]; then EXTRA="-fsanitize=address,undefined -fno-omit-frame-pointer"; fi
        OUT="/tmp/lifecycle-webui-${CC}-${MODE}-$$"
        "$CC" -std=c11 -O1 -g -Wall -Wextra -Werror -pthread $EXTRA \
            -Itests tests/test_snapshot.c -o "$OUT"
        "$OUT"
        rm "$OUT"
        echo "PASS $CC $MODE"
    done
done
