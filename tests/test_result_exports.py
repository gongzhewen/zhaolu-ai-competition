from __future__ import annotations

import unittest

from app.modules.exports.schemas import ExportTable, ResultExportRequest
from app.modules.exports.service import ExportDataError, build_export_file


class ResultExportTests(unittest.TestCase):
    def make_request(self, file_format: str) -> ResultExportRequest:
        return ResultExportRequest(
            kind="query",
            format=file_format,
            title="2026年招生计划分析",
            filename="招生计划分析",
            question="2026年招生计划数是多少？",
            answer="当前招生计划 6295 人。",
            metrics={"计划数": 6295, "录取数": 6287},
            sections=[{"title": "口径说明", "text": "数据来自受控工具。"}],
            table=ExportTable(
                columns=["专业", "计划数", "完成率"],
                rows=[["土木工程", 302, "99.67%"]],
            ),
        )

    def test_all_supported_formats_generate_binary_content(self) -> None:
        magic = {
            "csv": "\ufeff".encode("utf-8"),
            "xlsx": b"PK",
            "docx": b"PK",
            "pdf": b"%PDF",
            "md": b"#",
            "json": b"{",
        }
        for file_format, prefix in magic.items():
            with self.subTest(file_format=file_format):
                content, media_type, disposition = build_export_file(
                    self.make_request(file_format)
                )
                self.assertTrue(content.startswith(prefix))
                self.assertTrue(media_type)
                self.assertIn("attachment;", disposition)

    def test_sensitive_columns_are_rejected(self) -> None:
        request = ResultExportRequest(
            kind="query",
            format="xlsx",
            title="学生列表",
            table=ExportTable(
                columns=["姓名", "手机号"],
                rows=[["张三", "13800138000"]],
            ),
        )
        with self.assertRaises(ExportDataError):
            build_export_file(request)


if __name__ == "__main__":
    unittest.main()

