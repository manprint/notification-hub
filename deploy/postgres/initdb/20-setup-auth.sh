#!/bin/bash
# Script eseguito DENTRO il container PostgreSQL durante l'init
# Aggiunge trust per localhost al pg_hba.conf

PG_HBA_FILE="/var/lib/postgresql/data/pg_hba.conf"

# Attendi che il file esista (creato da PostgreSQL durante init)
until [ -f "$PG_HBA_FILE" ]; do
  sleep 1
done

# Aggiungi la linea per md5 su localhost (se non esiste già)
if ! grep -q "host.*all.*all.*127.0.0.1.*md5" "$PG_HBA_FILE"; then
  echo "host    all             all             127.0.0.1/32            md5" >> "$PG_HBA_FILE"
  echo "host    all             all             ::1/128                 md5" >> "$PG_HBA_FILE"
fi
