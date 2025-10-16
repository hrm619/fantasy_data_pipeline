"""
Data loading utilities for fantasy football data processing.

Simplified version of the original load_data function.
"""

import pandas as pd
import os


def load_data(filepath: str, header_row: int = None, sheet_name: str = None) -> pd.DataFrame:
    """
    Load a file into a pandas DataFrame based on its extension.
    Supports CSV and Excel (xlsx) files.

    Args:
        filepath (str): Path to the file.
        header_row (int, optional): Row index to use as column headers for CSV files.
                                   If None, auto-detects or uses default (0).
        sheet_name (str, optional): Specific sheet name to load from Excel files.
                                   If None, uses default logic (skip "Read Me" sheets).

    Returns:
        pd.DataFrame: Loaded data.

    Raises:
        ValueError: If the file extension is not supported.
    """
    if filepath.lower().endswith('.csv'):
        # Handle CSV files with flexible header row detection
        if header_row is not None:
            return pd.read_csv(filepath, header=header_row)
        else:
            # Auto-detect header row for CSV files
            try:
                # First try loading normally - this works for most cases
                df_test = pd.read_csv(filepath, nrows=5)

                # Check if the first row looks like a header (non-numeric values in most columns)
                # vs data rows (more likely to have numeric values)
                numeric_count_first = sum(pd.api.types.is_numeric_dtype(df_test[col]) for col in df_test.columns)
                total_cols = len(df_test.columns)

                # If most columns are non-numeric in the header, it's likely correctly loaded
                if numeric_count_first / total_cols < 0.5:
                    # Header is likely correct, reload full file
                    return pd.read_csv(filepath)

                # Otherwise try to detect actual header row
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = []
                    for i, line in enumerate(f):
                        lines.append(line.strip())
                        if i >= 10:  # Read first 10 lines for analysis
                            break

                # Check if any line after line 0 has significantly different content
                # (could indicate metadata rows before header)
                for i in range(1, min(len(lines), 5)):
                    if lines[i].lower().startswith(('player', 'rank', 'name', 'pos', 'team')):
                        # Found a likely header row
                        return pd.read_csv(filepath, header=i)

                # Default to first row as header
                return pd.read_csv(filepath)
                    
            except Exception:
                # Fallback to original method if file reading fails
                try:
                    return pd.read_csv(filepath)
                except pd.errors.ParserError:
                    # Last resort - skip bad lines
                    return pd.read_csv(filepath, on_bad_lines='skip')
                    
    elif filepath.lower().endswith(('.xlsx', '.xls')):
        # Handle Excel files
        xl = pd.ExcelFile(filepath)
        sheet_names = xl.sheet_names

        # If specific sheet name is provided, use it
        if sheet_name is not None:
            if sheet_name in sheet_names:
                return pd.read_excel(filepath, sheet_name=sheet_name)
            else:
                raise ValueError(f"Sheet '{sheet_name}' not found in {filepath}. Available sheets: {sheet_names}")

        # Otherwise, if first sheet is "Read Me", load second sheet
        if sheet_names and sheet_names[0].strip().lower() == "read me":
            if len(sheet_names) > 1:
                return pd.read_excel(filepath, sheet_name=sheet_names[1])
            else:
                raise ValueError(f"Excel file {filepath} has only a 'Read Me' sheet and no data sheet.")
        else:
            return pd.read_excel(filepath, sheet_name=sheet_names[0])
    else:
        raise ValueError(f"Unsupported file type for: {filepath}")
