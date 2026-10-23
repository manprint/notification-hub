#!/bin/bash
# Script eseguito DENTRO il container PostgreSQL durante l'init
#
# Il pg_hba.conf dell'immagine ufficiale ha le righe trust per 127.0.0.1 e ::1 (anche quelle di
# replication) prima della regola generale scram-sha-256. PostgreSQL usa la prima regola che
# corrisponde, quindi aggiungere righe in coda non serve a nulla: qui le righe trust del loopback
# passano a scram-sha-256. La riga local (socket Unix) resta trust, e la usano gli script di init.

PG_HBA_FILE="${PGDATA:-/var/lib/postgresql/data}/pg_hba.conf"

# Attendi che il file esista (creato da PostgreSQL durante init)
until [ -f "$PG_HBA_FILE" ]; do
  sleep 1
done

sed -i -E \
  's/^(host[[:space:]]+[^[:space:]]+[[:space:]]+[^[:space:]]+[[:space:]]+(127\.0\.0\.1\/32|::1\/128)[[:space:]]+)trust/\1scram-sha-256/' \
  "$PG_HBA_FILE"
