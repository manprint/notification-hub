-- Development passwords for docker-compose, not for production
CREATE ROLE notifyhub_owner  LOGIN PASSWORD 'dev_owner'  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE notifyhub_app    LOGIN PASSWORD 'dev_app'    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE notifyhub_ingest LOGIN PASSWORD 'dev_ingest' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
CREATE ROLE notifyhub_auth   LOGIN PASSWORD 'dev_auth'   NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

ALTER SCHEMA public OWNER TO notifyhub_owner;
GRANT USAGE ON SCHEMA public TO notifyhub_app, notifyhub_ingest, notifyhub_auth;
