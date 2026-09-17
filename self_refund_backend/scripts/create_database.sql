-- Creates the AutoRefund database login and database (idempotent).
-- Run as the PostgreSQL superuser, e.g. from init-database.bat or:
--   psql -U postgres -h localhost -v db_password=YOUR_PASSWORD -f scripts/create_database.sql
\set ON_ERROR_STOP on

SELECT 'CREATE ROLE refund_user LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'refund_user')\gexec

ALTER ROLE refund_user WITH LOGIN PASSWORD :'db_password';

SELECT 'CREATE DATABASE refund_kiosk OWNER refund_user ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'refund_kiosk')\gexec
