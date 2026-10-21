"""Point the app at a throwaway test database BEFORE anything imports app.db.session.
Database tests (tests/database) rebuild it from sql/schema.sql; unit tests never touch it."""
import os

TEST_DB_URL = "mysql+pymysql://root:@127.0.0.1:3306/carpark_test?charset=utf8mb4"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", TEST_DB_URL)
