#!/bin/sh
# Backs up the database and every uploaded photo, video and document.
#
#   backup.sh            run one backup now
#   backup.sh --daemon   run every night at GP_BACKUP_HOUR (default 2, i.e. 02:00 in TZ)
#
# What a run leaves at the destination (see common.sh):
#   db/greenplot-<stamp>.dump        pg_dump custom format, one per night (<stamp> is UTC, e.g. 2026-11-01T2030Z)
#   media/current/...                a mirror of the uploads as they are now
#   media/changed/<stamp>/...        files that run deleted or overwritten in the mirror
# Dumps and media/changed folders older than GP_BACKUP_RETENTION_DAYS (default 30) are removed, so any
# night in that window can be restored. GP_BACKUP_HEARTBEAT_URL (Healthchecks.io style) is pinged on
# success and <url>/fail on failure, so a missed or broken night raises an alert.
set -eu
. /usr/local/bin/common.sh

ping() {
  [ -n "${GP_BACKUP_HEARTBEAT_URL:-}" ] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null "${GP_BACKUP_HEARTBEAT_URL%/}$1" || log "heartbeat ping failed"
}

# Deletes entries under $1 whose name starts with a date (after an optional prefix $2) before the cutoff.
prune() {
  cutoff="$(date -d "@$(( $(date +%s) - RETENTION_DAYS * 86400 ))" +%Y-%m-%d)"
  # Names are our own stamps (no spaces), so word splitting is safe and keeps errors fatal under set -e.
  for name in $(rclone lsf "$1" 2>/dev/null); do
    day="$(echo "${name#"$2"}" | cut -c1-10)"
    expr "$day" : '[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}$' >/dev/null || continue
    expr "$day" \< "$cutoff" >/dev/null || continue
    log "removing $1/$name (older than $RETENTION_DAYS days)"
    case "$name" in
      */) rclone purge "$1/${name%/}" ;;
      *) rclone deletefile "$1/$name" ;;
    esac
  done
}

run_once() {
  stamp="$(date -u +%Y-%m-%dT%H%MZ)"  # UTC, so names sort in time order whatever TZ is
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  [ "$OFF_SERVER" = 1 ] || log "WARNING: GP_BACKUP_S3_BUCKET is not set, so backups stay on this server only"

  log "dumping database $PGDATABASE"
  pg_dump --format=custom --no-owner --file="$work/db.dump" "$PGDATABASE"
  pg_restore --list "$work/db.dump" >/dev/null  # an unreadable dump fails the run
  rclone copyto "$work/db.dump" "$DEST/db/greenplot-$stamp.dump"
  log "database saved: db/greenplot-$stamp.dump ($(du -h "$work/db.dump" | cut -f1))"

  log "copying uploads from $MEDIA_SRC"
  rclone sync "$MEDIA_SRC" "$DEST/media/current" --backup-dir "$DEST/media/changed/$stamp" --stats-one-line --stats-log-level NOTICE
  log "uploads saved: media/current ($(rclone size "$DEST/media/current" | tr '\n' ' '))"

  prune "$DEST/db" "greenplot-"
  prune "$DEST/media/changed" ""
  rm -rf "$work"
  trap - EXIT
  log "backup $stamp finished"
}

# run_once goes in its own process: inside `if`, set -e would stop applying to it.
attempt() {
  if "$0" --run-once; then ping ""; else log "backup FAILED"; ping "/fail"; return 1; fi
}

case "${1:-}" in
  --run-once) run_once; exit ;;
  --daemon) ;;
  *) attempt; exit ;;
esac

hour="${GP_BACKUP_HOUR:-2}"
log "scheduled daily at $(printf '%02d' "$hour"):00 $(date +%Z), keeping $RETENTION_DAYS days, to $DEST"
while :; do
  now="$(date +%s)"
  next="$(date -d "$(date +%Y-%m-%d) $(printf '%02d' "$hour"):00:00" +%s)"
  [ "$next" -gt "$now" ] || next=$(( next + 86400 ))
  sleep $(( next - now ))
  attempt || true
done
