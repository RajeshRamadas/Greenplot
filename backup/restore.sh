#!/bin/sh
# Restores from the backups that backup.sh makes. Run inside the backup container:
#   docker compose exec backup restore.sh <command>
#
#   list                            show the database backups and the media change folders
#   check [DUMP]                    test-restore a dump (default: the latest) into a scratch database,
#                                   count its rows, then drop it; the live database is not touched
#   db DUMP|latest --yes            replace the live database with DUMP; stop api and worker first
#   media --yes                     copy media/current back over the uploads (adds missing files,
#                                   replaces changed ones, deletes nothing)
# A file deleted or overwritten after the mirror was made is in media/changed/<stamp>/ under the same path.
set -eu
. /usr/local/bin/common.sh

latest_dump() { rclone lsf "$DEST/db" --files-only | sort | tail -n 1; }

fetch() {
  name="$1"
  [ "$name" = latest ] && name="$(latest_dump)"
  [ -n "$name" ] || { log "no database backups found in $DEST/db"; exit 1; }
  rclone copyto "$DEST/db/$name" "$2"
  log "fetched db/$name"
}

cmd="${1:-}"
case "$cmd" in
  list)
    echo "Database backups ($DEST/db):"; rclone lsl "$DEST/db" | sort -k4
    echo; echo "Media change folders ($DEST/media/changed):"; rclone lsf --dirs-only "$DEST/media/changed" 2>/dev/null || true
    echo; echo "Media mirror: $(rclone size "$DEST/media/current" | tr '\n' ' ')"
    ;;
  check)
    work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
    fetch "${2:-latest}" "$work/db.dump"
    scratch="greenplot_restore_check"
    dropdb --if-exists "$scratch"
    createdb "$scratch"
    pg_restore --no-owner --exit-on-error --dbname="$scratch" "$work/db.dump"
    tables="$(psql -At -d "$scratch" -c "select count(*) from information_schema.tables where table_schema = 'public'")"
    users="$(psql -At -d "$scratch" -c "select count(*) from users")"
    version="$(psql -At -d "$scratch" -c "select version_num from alembic_version" | tr '\n' ' ')"
    dropdb "$scratch"
    log "restore check passed: $tables tables, $users users, migration $version"
    ;;
  db)
    [ "${3:-}" = "--yes" ] || { echo "This replaces the live database. Stop api and worker, then add --yes."; exit 2; }
    work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
    fetch "${2:?which dump? see restore.sh list}" "$work/db.dump"
    dropdb --force "$PGDATABASE"
    createdb "$PGDATABASE"
    pg_restore --no-owner --exit-on-error --dbname="$PGDATABASE" "$work/db.dump"
    log "database restored; start api and worker again"
    ;;
  media)
    [ "${2:-}" = "--yes" ] || { echo "This copies media/current over the uploads in $MEDIA_SRC. Add --yes."; exit 2; }
    rclone copy "$DEST/media/current" "$MEDIA_SRC" --stats-one-line --stats-log-level NOTICE
    log "uploads restored"
    ;;
  *)
    sed -n '2,11p' "$0"; exit 2
    ;;
esac
