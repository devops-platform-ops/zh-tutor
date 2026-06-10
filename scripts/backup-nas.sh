#!/usr/bin/env bash
# zh-tutor → NAS 백업 (mbp15 이중화)
#
# zh-tutor 는 gitlab.dop 원격이 있어 코드는 이미 원격(→msu→NAS)에 있으나,
# (1) mbp15→NAS 직접 이중화 + (2) workspaces 밖 비-git 데이터(~/.local/share/zh-tutor:
# HSK 캐시·진도 등)는 어디에도 백업 안 됨 → 이 스크립트로 NAS(SMB) 미러.
#
# 사용:  bash scripts/backup-nas.sh   |   NAS_DIR=/다른/경로 bash scripts/backup-nas.sh
# 주의:  --delete 미러(스냅샷 아님).
set -uo pipefail

NAS_DIR="${NAS_DIR:-/Volumes/Working/mbp15-backup/zh-tutor}"
MOUNT="/Volumes/Working"
[ -d "$MOUNT" ] || { echo "✗ NAS 미마운트: $MOUNT  (Finder ⌘K → smb://nas-k010k.local)" >&2; exit 1; }

RSYNC=(rsync -aL --safe-links --inplace --no-specials --delete --modify-window=1 --exclude .DS_Store)

FAILED=0
backup() {  # $1=라벨 $2=src(끝 슬래시) $3=dst하위 ; $4..=추가 exclude
  local label="$1" src="$2" sub="$3"; shift 3
  if [ ! -e "${src%/}" ]; then echo "  SKIP $label (소스 없음: $src)"; return 0; fi
  mkdir -p "$NAS_DIR/$sub"
  "${RSYNC[@]}" "$@" "$src" "$NAS_DIR/$sub/"
  local rc=$?
  if [ "$rc" -eq 0 ] || [ "$rc" -eq 23 ] || [ "$rc" -eq 24 ]; then
    echo "  OK   $label → $sub/ (rc=$rc)"
  else echo "  FAIL $label (rc=$rc)" >&2; FAILED=1; fi
}

echo "zh-tutor → $NAS_DIR"
backup "코드+git" "$HOME/workspaces/personal/zh-tutor/" "repo" --exclude .venv/ --exclude __pycache__/
backup "로컬데이터" "$HOME/.local/share/zh-tutor/"      "share"

[ "$FAILED" -eq 0 ] && echo "✅ 백업 완료: $NAS_DIR" || { echo "✗ 일부 실패" >&2; exit 1; }
