import pytest
import pandas as pd
import json


@pytest.fixture
def tmp_csv(tmp_path):
    """Create a simple CSV file for testing."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text("NAME,AGE,SCORE\nAlice,30,95\nBob,25,88\n")
    return str(csv_path)


@pytest.fixture
def tmp_csv_with_metadata(tmp_path):
    """Create a CSV file with metadata rows before the header."""
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text("Source: Test\nDate: 2025-01-01\nNAME,AGE,SCORE\nAlice,30,95\nBob,25,88\n")
    return str(csv_path)


@pytest.fixture
def tmp_excel(tmp_path):
    """Create a simple Excel file for testing."""
    xlsx_path = tmp_path / "test.xlsx"
    df = pd.DataFrame({"NAME": ["Alice", "Bob"], "SCORE": [95, 88]})
    df.to_excel(str(xlsx_path), index=False, sheet_name="Data")
    return str(xlsx_path)


@pytest.fixture
def tmp_excel_with_readme(tmp_path):
    """Create an Excel file where the first sheet is 'Read Me'."""
    xlsx_path = tmp_path / "readme.xlsx"
    with pd.ExcelWriter(str(xlsx_path)) as writer:
        pd.DataFrame({"Info": ["This is a readme"]}).to_excel(writer, sheet_name="Read Me", index=False)
        pd.DataFrame({"NAME": ["Alice"], "SCORE": [95]}).to_excel(writer, sheet_name="Data", index=False)
    return str(xlsx_path)


@pytest.fixture
def tmp_player_key(tmp_path):
    """Create a player key dictionary JSON file."""
    player_key = {
        "MahomPa01": ["Patrick Mahomes", "Pat Mahomes"],
        "HillTy01": ["Tyreek Hill"],
        "JeffJa01": ["Ja'Marr Chase", "JaMarr Chase"],
    }
    key_path = tmp_path / "player_key_dict.json"
    key_path.write_text(json.dumps(player_key, indent=2))
    return str(key_path)


@pytest.fixture
def sample_player_df():
    """Create a sample DataFrame with player names."""
    return pd.DataFrame({
        "PLAYER NAME": ["Patrick Mahomes", "Tyreek Hill", "Unknown Player"],
        "POS": ["QB", "WR", "RB"],
        "TEAM": ["KC", "MIA", "???"],
    })
