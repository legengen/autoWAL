import json
import random
import unittest
from unittest.mock import patch

from autowal.filler import (
    build_matrix_script,
    build_matrix_verification_script,
    fill_matrix_scale,
)


MATRIX_ITEM = {
    "formItemId": "matrix-demo",
    "title": "矩阵评分",
    "rows": [
        {"id": 101, "label": "第一行"},
        {"id": 102, "label": "第二行"},
        {"id": 103, "label": "第三行"},
    ],
}


class FakeDriver:
    def __init__(self):
        self.script = None
        self.scripts = []

    def execute_script(self, script):
        self.script = script
        self.scripts.append(script)
        if "removeAttribute('data-autowal-matrix-row')" in script:
            return json.dumps([
                {"index": index, "selected": 7}
                for index, _row in enumerate(MATRIX_ITEM["rows"])
            ])
        return json.dumps([
            {"row": row["label"], "index": index, "ok": True}
            for index, row in enumerate(MATRIX_ITEM["rows"])
        ])


class MatrixScaleTests(unittest.TestCase):
    def test_script_uses_row_ids_and_rejects_duplicate_containers(self):
        script = build_matrix_script(MATRIX_ITEM, 8)

        self.assertIn('"id": 101', script)
        self.assertIn('"id": 102', script)
        self.assertIn('findByRowId(rowSpec)', script)
        self.assertIn("duplicate_row_container", script)
        self.assertIn("if (best === matrix && ROWS.length > 1) return null", script)
        self.assertIn(".mobile-matrix-scale > .card", script)
        self.assertIn("data-autowal-matrix-row", script)

        verification = build_matrix_verification_script(MATRIX_ITEM)
        self.assertIn("selection_not_applied", fill_matrix_scale.__code__.co_consts)
        self.assertIn("aria-valuenow", verification)
        self.assertIn("removeAttribute('data-autowal-matrix-row')", verification)

    @patch("autowal.filler._emit")
    def test_fill_matrix_sends_all_rows_to_browser(self, emit):
        driver = FakeDriver()

        fill_matrix_scale(driver, MATRIX_ITEM, random.Random(1))

        self.assertIsNotNone(driver.script)
        click_script = driver.scripts[0]
        for row in MATRIX_ITEM["rows"]:
            self.assertIn(str(row["id"]), click_script)
            self.assertIn(row["label"], click_script)
        self.assertIn("3/3", emit.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
