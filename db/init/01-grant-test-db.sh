#!/bin/bash
# Runs once on first init of the MySQL volume. Django's test runner creates a
# separate `test_<name>` database, which the non-root app user may not do
# without this grant.
mysql -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
GRANT ALL PRIVILEGES ON \`test\_%\`.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;
SQL
