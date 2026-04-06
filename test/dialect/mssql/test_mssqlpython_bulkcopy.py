"""Tests for use_bulkcopy support in the mssqlpython dialect."""

from unittest.mock import MagicMock

from sqlalchemy.dialects.mssql.mssqlpython import MSDialect_mssqlpython


class TestExtractInsertTable:
    def test_simple(self):
        assert (
            MSDialect_mssqlpython._extract_insert_table(
                "INSERT INTO Users (id, name) VALUES (?, ?)"
            )
            == "Users"
        )

    def test_schema_qualified(self):
        assert (
            MSDialect_mssqlpython._extract_insert_table(
                "INSERT INTO dbo.Users (id, name) VALUES (?, ?)"
            )
            == "dbo.Users"
        )

    def test_bracketed(self):
        assert (
            MSDialect_mssqlpython._extract_insert_table(
                "INSERT INTO [dbo].[Users] (id, name) VALUES (?, ?)"
            )
            == "[dbo].[Users]"
        )

    def test_three_part(self):
        assert (
            MSDialect_mssqlpython._extract_insert_table(
                "INSERT INTO mydb.dbo.Users (id, name) VALUES (?, ?)"
            )
            == "mydb.dbo.Users"
        )

    def test_non_insert_returns_none(self):
        assert (
            MSDialect_mssqlpython._extract_insert_table(
                "UPDATE Users SET name = ? WHERE id = ?"
            )
            is None
        )

    def test_select_returns_none(self):
        assert (
            MSDialect_mssqlpython._extract_insert_table("SELECT * FROM Users")
            is None
        )


class TestDoExecutemanyBulkcopy:
    INSERT_SQL = "INSERT INTO dbo.Users (id, name) VALUES (?, ?)"

    def _make_cursor(self):
        cursor = MagicMock()
        cursor.bulkcopy.return_value = {
            "rows_copied": 2,
            "batch_count": 1,
            "elapsed_time": 0.01,
        }
        return cursor

    def test_routes_insert_through_bulkcopy(self):
        dialect = MSDialect_mssqlpython(use_bulkcopy=True)
        cursor = self._make_cursor()
        params = [(1, "Alice"), (2, "Bob")]

        dialect.do_executemany(cursor, self.INSERT_SQL, params)

        cursor.bulkcopy.assert_called_once()
        kw = cursor.bulkcopy.call_args.kwargs
        assert kw["table_name"] == "dbo.Users"
        assert kw["data"] == [(1, "Alice"), (2, "Bob")]
        assert kw["batch_size"] == 10000
        assert kw["table_lock"] is True
        cursor.executemany.assert_not_called()

    def test_custom_batch_size_and_lock(self):
        dialect = MSDialect_mssqlpython(
            use_bulkcopy=True,
            bulkcopy_batch_size=500,
            bulkcopy_table_lock=False,
        )
        cursor = self._make_cursor()

        dialect.do_executemany(cursor, self.INSERT_SQL, [(1, "A")])

        kw = cursor.bulkcopy.call_args.kwargs
        assert kw["batch_size"] == 500
        assert kw["table_lock"] is False

    def test_dict_params_converted(self):
        dialect = MSDialect_mssqlpython(use_bulkcopy=True)
        cursor = self._make_cursor()
        params = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

        dialect.do_executemany(cursor, self.INSERT_SQL, params)

        data = cursor.bulkcopy.call_args.kwargs["data"]
        assert data == [(1, "Alice"), (2, "Bob")]

    def test_disabled_uses_executemany(self):
        dialect = MSDialect_mssqlpython(use_bulkcopy=False)
        cursor = self._make_cursor()
        params = [(1, "A")]

        dialect.do_executemany(cursor, self.INSERT_SQL, params)

        cursor.executemany.assert_called_once()
        cursor.bulkcopy.assert_not_called()

    def test_non_insert_uses_executemany(self):
        dialect = MSDialect_mssqlpython(use_bulkcopy=True)
        cursor = self._make_cursor()
        sql = "UPDATE Users SET name = ? WHERE id = ?"

        dialect.do_executemany(cursor, sql, [(1, "A")])

        cursor.executemany.assert_called_once()
        cursor.bulkcopy.assert_not_called()

    def test_empty_params_uses_executemany(self):
        dialect = MSDialect_mssqlpython(use_bulkcopy=True)
        cursor = self._make_cursor()

        dialect.do_executemany(cursor, self.INSERT_SQL, [])

        cursor.executemany.assert_called_once()

    def test_fallback_on_bulkcopy_error(self):
        dialect = MSDialect_mssqlpython(use_bulkcopy=True)
        cursor = self._make_cursor()
        cursor.bulkcopy.side_effect = RuntimeError("TDS error")
        params = [(1, "A")]

        dialect.do_executemany(cursor, self.INSERT_SQL, params)

        cursor.bulkcopy.assert_called_once()
        cursor.executemany.assert_called_once()

    def test_no_bulkcopy_attr_uses_executemany(self):
        dialect = MSDialect_mssqlpython(use_bulkcopy=True)
        cursor = MagicMock(spec=["executemany", "execute"])  # no bulkcopy
        params = [(1, "A")]

        dialect.do_executemany(cursor, self.INSERT_SQL, params)

        cursor.executemany.assert_called_once()


class TestBulkcopyConfig:
    def test_default_disabled(self):
        d = MSDialect_mssqlpython()
        assert d.use_bulkcopy is False

    def test_enabled(self):
        d = MSDialect_mssqlpython(use_bulkcopy=True)
        assert d.use_bulkcopy is True
        assert d.bulkcopy_batch_size == 10000
        assert d.bulkcopy_table_lock is True
        assert d.use_insertmanyvalues_wo_returning is False

    def test_insertmanyvalues_unchanged_when_disabled(self):
        d = MSDialect_mssqlpython(use_bulkcopy=False)
        # should not have been explicitly set to False
        assert d.use_bulkcopy is False
