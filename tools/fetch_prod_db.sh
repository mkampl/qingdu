#!/usr/bin/env bash
# Pull a consistent, read-only copy of the production SQLite DB for local
# staging tests. Goes through Ansible (no direct root SSH to the VPS).
#
#   tools/fetch_prod_db.sh /path/outside/the/repo
#
# The copy is made with SQLite's online backup API inside the container, so
# it is consistent even while the app is writing. It contains real user data:
# keep it out of the repo and out of data/, and delete it when done.
#
# Environment overrides:
#   QINGDU_ANSIBLE_DIR   Ansible checkout          (default /root/ITvoodooSetup)
#   QINGDU_ANSIBLE_HOST  inventory host             (default 37.120.189.127)
#   QINGDU_VAULT_PASS    vault password file        (default /root/.vault_pass)
#   QINGDU_CONTAINER     app container name         (default chinese_analyzer)
#   QINGDU_DB_PATH       DB path inside container   (default /app/data/qingdu.db)
set -euo pipefail

usage() {
    echo "usage: $0 DEST_DIR" >&2
    echo "  DEST_DIR must be outside the repository." >&2
    exit 2
}

[[ $# -eq 1 ]] || usage

ANSIBLE_DIR=${QINGDU_ANSIBLE_DIR:-/root/ITvoodooSetup}
HOST=${QINGDU_ANSIBLE_HOST:-37.120.189.127}
VAULT_PASS=${QINGDU_VAULT_PASS:-/root/.vault_pass}
CONTAINER=${QINGDU_CONTAINER:-chinese_analyzer}
DB_PATH=${QINGDU_DB_PATH:-/app/data/qingdu.db}

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
DEST=$(realpath -m -- "$1")

case "$DEST/" in
    "$REPO_ROOT"/*)
        echo "refusing: $DEST is inside the repository ($REPO_ROOT)" >&2
        exit 1
        ;;
esac

mkdir -p -- "$DEST"
DEST=$(cd "$DEST" && pwd -P)
case "$DEST/" in
    "$REPO_ROOT"/*)
        echo "refusing: $DEST resolves to a path inside the repository" >&2
        exit 1
        ;;
esac

STAMP=$(date +%Y%m%d-%H%M%S)
REMOTE_TMP="/tmp/qingdu-copy-$STAMP.db"
LOCAL_FILE="$DEST/qingdu-prod-$STAMP.db"

export LC_ALL=C.UTF-8
cd "$ANSIBLE_DIR"

ans() {
    ansible "$HOST" -i inventory --vault-password-file "$VAULT_PASS" \
        -e @vars/vault_vars.yml "$@"
}

cleanup() {
    ans -m shell -a "docker exec $CONTAINER rm -f $REMOTE_TMP; rm -f $REMOTE_TMP" >/dev/null || \
        echo "warning: could not remove $REMOTE_TMP on $HOST" >&2
}
trap cleanup EXIT

# The backup API only reads from the source DB; the copy is written to the
# container's /tmp, then copied out to the host's /tmp for the fetch.
BACKUP_PY="import sqlite3; s = sqlite3.connect('$DB_PATH'); d = sqlite3.connect('$REMOTE_TMP'); s.backup(d); d.close(); s.close()"

echo "Backing up $CONTAINER:$DB_PATH on $HOST ..." >&2
ans -m shell -a "set -e; docker exec $CONTAINER python -c \"$BACKUP_PY\"; \
docker cp $CONTAINER:$REMOTE_TMP $REMOTE_TMP; chmod 600 $REMOTE_TMP"

echo "Fetching to $LOCAL_FILE ..." >&2
ans -m fetch -a "src=$REMOTE_TMP dest=$LOCAL_FILE flat=yes"

chmod 400 "$LOCAL_FILE"
python3 - "$LOCAL_FILE" <<'EOF'
import sqlite3
import sys

con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
result = con.execute("PRAGMA integrity_check").fetchone()[0]
users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
print(f"integrity_check: {result}; users: {users}", file=sys.stderr)
con.close()
sys.exit(0 if result == "ok" else 1)
EOF

echo "$LOCAL_FILE"
