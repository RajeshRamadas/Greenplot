# Shared settings for backup.sh and restore.sh. Sourced, not run.
#
# Where backups go: a private S3 / Cloudflare R2 bucket when GP_BACKUP_S3_BUCKET is set, otherwise the
# `backups` Docker volume (/backups). The volume lives on the same server, so it does not survive losing
# the server; use it only for testing.
#
# Where uploads come from: the media bucket when GP_STORAGE_BACKEND=s3, otherwise the media volume.

export RCLONE_CONFIG="${RCLONE_CONFIG:-/dev/null}"  # all remotes come from the environment

log() { echo "$(date '+%Y-%m-%d %H:%M:%S %Z') backup: $*"; }

: "${PGHOST:=db}" "${PGUSER:=greenplot}" "${PGDATABASE:=greenplot}"
export PGHOST PGUSER PGDATABASE
RETENTION_DAYS="${GP_BACKUP_RETENTION_DAYS:-30}"

if [ -n "${GP_BACKUP_S3_BUCKET:-}" ]; then
  export RCLONE_CONFIG_BACKUP_TYPE=s3
  export RCLONE_CONFIG_BACKUP_PROVIDER="${GP_BACKUP_S3_PROVIDER:-Cloudflare}"
  export RCLONE_CONFIG_BACKUP_ENDPOINT="${GP_BACKUP_S3_ENDPOINT_URL:-}"
  export RCLONE_CONFIG_BACKUP_ACCESS_KEY_ID="${GP_BACKUP_S3_ACCESS_KEY:-}"
  export RCLONE_CONFIG_BACKUP_SECRET_ACCESS_KEY="${GP_BACKUP_S3_SECRET_KEY:-}"
  export RCLONE_CONFIG_BACKUP_REGION="${GP_BACKUP_S3_REGION:-auto}"
  export RCLONE_CONFIG_BACKUP_NO_CHECK_BUCKET=true
  DEST="backup:${GP_BACKUP_S3_BUCKET}/${GP_BACKUP_PREFIX:-greenplot}"
  OFF_SERVER=1
else
  DEST="/backups"
  OFF_SERVER=0
fi

if [ "${GP_STORAGE_BACKEND:-local}" = "s3" ]; then
  export RCLONE_CONFIG_MEDIA_TYPE=s3
  export RCLONE_CONFIG_MEDIA_PROVIDER="${GP_BACKUP_S3_PROVIDER:-Cloudflare}"
  export RCLONE_CONFIG_MEDIA_ENDPOINT="${GP_S3_ENDPOINT_URL:-}"
  export RCLONE_CONFIG_MEDIA_ACCESS_KEY_ID="${GP_S3_ACCESS_KEY:-}"
  export RCLONE_CONFIG_MEDIA_SECRET_ACCESS_KEY="${GP_S3_SECRET_KEY:-}"
  export RCLONE_CONFIG_MEDIA_REGION="${GP_S3_REGION:-auto}"
  export RCLONE_CONFIG_MEDIA_NO_CHECK_BUCKET=true
  MEDIA_SRC="media:${GP_S3_BUCKET:-greenplot-media}"
else
  MEDIA_SRC="/data/storage"
fi
