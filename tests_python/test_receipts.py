"""Committed receipts must be reproducible: nothing that changes from one run or machine to the next."""

from pathlib import Path
import tempfile
import unittest

from scripts import export_evidence, lint_sql, run_all, verify_snowflake_compile


def run_results(started, thread, seconds):
    return {
        'metadata': {
            'dbt_version': '1.12.5',
            'dbt_schema_version': 'run-results/v6',
            'generated_at': started,
            'invocation_id': thread,
        },
        'elapsed_time': seconds,
        'args': {'project_dir': f'/home/{thread}'},
        'results': [
            {
                'unique_id': 'test.b',
                'status': 'pass',
                'failures': 0,
                'message': None,
                'thread_id': thread,
                'execution_time': seconds,
                'timing': [{'started_at': started}],
                'compiled_code': 'select 1',
            },
            {
                'unique_id': 'model.a',
                'status': 'success',
                'failures': None,
                'message': 'OK',
                'thread_id': thread,
                'execution_time': seconds,
                'timing': [{'started_at': started}],
                'compiled_code': 'select 1',
            },
        ],
    }


class ReceiptsTest(unittest.TestCase):
    def test_build_receipt_is_identical_across_runs_and_keeps_every_outcome(self):
        first = run_all.build_receipt(run_results('2026-01-01T00:00:00Z', 'Thread-1', 1.5))
        second = run_all.build_receipt(run_results('2026-06-30T12:00:00Z', 'Thread-7', 9.0))
        self.assertEqual(first, second)
        self.assertEqual([r['unique_id'] for r in first['results']], ['model.a', 'test.b'])
        self.assertEqual(first['results'][1], {'unique_id': 'test.b', 'status': 'pass', 'failures': 0, 'message': None})

    def test_build_receipt_keeps_a_failure_visible(self):
        results = run_results('2026-01-01T00:00:00Z', 'Thread-1', 1.5)
        results['results'][0].update(status='fail', failures=3, message='Got 3 results, configured to fail if != 0')
        failed = run_all.build_receipt(results)['results'][1]
        self.assertEqual((failed['status'], failed['failures']), ('fail', 3))

    def test_load_manifest_keeps_file_hashes_and_drops_machine_details(self):
        manifest = {
            'loaded_at_utc': '2026-01-01T00:00:00+00:00',
            'python': '3.12.3',
            'duckdb': '1.5.6',
            'files': [{'file': 'pos.csv', 'sha256': 'abc', 'tables': {'pos': 3}}],
        }
        self.assertEqual(
            export_evidence.portable_manifest(manifest),
            {'duckdb': '1.5.6', 'files': [{'file': 'pos.csv', 'sha256': 'abc', 'tables': {'pos': 3}}]},
        )

    def test_lint_receipt_drops_timings_and_sorts_files(self):
        report = [
            {'filepath': 'models/b.sql', 'violations': [{'code': 'LT01'}], 'timings': {'linting': 0.2}},
            {'filepath': 'models/a.sql', 'violations': [], 'timings': {'linting': 0.1}, 'statistics': {}},
        ]
        self.assertEqual(
            lint_sql.lint_receipt(report),
            [
                {'filepath': 'models/a.sql', 'violations': []},
                {'filepath': 'models/b.sql', 'violations': [{'code': 'LT01'}]},
            ],
        )


class SnowflakeCompileCheckTest(unittest.TestCase):
    GOOD = "select try_to_date(week_ending, 'YYYY-MM-DD') as d from raw.pos where regexp_like(trim(upc), '[0-9]+')"

    def compiled(self, **models):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        for name, sql in models.items():
            (Path(temporary.name) / f'{name}.sql').write_text(sql, encoding='utf-8')
        return Path(temporary.name)

    def test_snowflake_sql_with_the_dispatched_functions_is_clean(self):
        folder = self.compiled(stg_pos_audit=self.GOOD, dim_item='select 1 as sku_id')
        self.assertEqual(verify_snowflake_compile.check_compiled(folder, {'stg_pos_audit', 'dim_item'}), [])

    def test_a_surviving_duckdb_function_a_syntax_error_and_a_missing_model_are_each_reported(self):
        folder = self.compiled(
            stg_pos_audit="select cast(try_strptime(week_ending, '%Y-%m-%d') as date) as d",
            dim_item='select from where',
        )
        problems = verify_snowflake_compile.check_compiled(folder, {'stg_pos_audit', 'dim_item', 'dim_store'})
        self.assertIn('dim_store was not compiled', problems)
        self.assertIn('stg_pos_audit still calls DuckDB-only try_strptime()', problems)
        self.assertTrue(any(p.startswith('dim_item does not parse as Snowflake SQL') for p in problems), problems)
        self.assertIn('stg_pos_audit does not use the Snowflake implementation try_to_date()', problems)


if __name__ == '__main__':
    unittest.main()
