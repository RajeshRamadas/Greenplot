# Nightly backups of the database and uploaded media (see backup.sh).
# pg_dump must match the server's major version (postgis/postgis:16); Ubuntu 24.04 ships PostgreSQL 16.
FROM ubuntu:24.04

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      postgresql-client-16 rclone curl ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY backup.sh restore.sh common.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh

CMD ["backup.sh", "--daemon"]
