import pytest
import pandas as pd
from fantasy_pipeline.data.loader import load_data


class TestLoadDataCSV:
    def test_loads_simple_csv(self, tmp_csv):
        df = load_data(tmp_csv)
        assert len(df) == 2
        assert list(df.columns) == ["NAME", "AGE", "SCORE"]

    def test_explicit_header_row(self, tmp_csv):
        df = load_data(tmp_csv, header_row=0)
        assert list(df.columns) == ["NAME", "AGE", "SCORE"]

    def test_auto_detects_header_after_metadata(self, tmp_csv_with_metadata):
        df = load_data(tmp_csv_with_metadata)
        assert "NAME" in df.columns
        assert len(df) == 2


class TestLoadDataExcel:
    def test_loads_simple_excel(self, tmp_excel):
        df = load_data(tmp_excel)
        assert len(df) == 2
        assert "NAME" in df.columns

    def test_skips_readme_sheet(self, tmp_excel_with_readme):
        df = load_data(tmp_excel_with_readme)
        assert "NAME" in df.columns
        assert "Info" not in df.columns

    def test_explicit_sheet_name(self, tmp_excel_with_readme):
        df = load_data(tmp_excel_with_readme, sheet_name="Data")
        assert "NAME" in df.columns

    def test_explicit_sheet_name_readme(self, tmp_excel_with_readme):
        df = load_data(tmp_excel_with_readme, sheet_name="Read Me")
        assert "Info" in df.columns


class TestLoadDataErrors:
    def test_unsupported_extension(self, tmp_path):
        txt_path = tmp_path / "file.txt"
        txt_path.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported file type"):
            load_data(str(txt_path))
