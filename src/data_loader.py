"""
Data loading utilities for fantasy football data processing.

Simplified version of the original load_data function.
"""

import pandas as pd
import os


def load_data(filepath: str, header_row: int = None) -> pd.DataFrame:
    """
    Load a file into a pandas DataFrame based on its extension.
    Supports CSV and Excel (xlsx) files.

    Args:
        filepath (str): Path to the file.
        header_row (int, optional): Row index to use as column headers for CSV files.
                                   If None, auto-detects or uses default (0).

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
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = []
                    for i, line in enumerate(f):
                        lines.append(line.strip())
                        if i >= 10:  # Read first 10 lines for analysis
                            break
                
                # Find the first line that looks like a proper CSV header
                header_row_idx = 0
                max_fields = 0
                
                for i, line in enumerate(lines):
                    if line and ',' in line:
                        field_count = len(line.split(','))
                        if field_count > max_fields:
                            max_fields = field_count
                            header_row_idx = i
                
                # If we found a line with multiple fields that's not the first line,
                # it's likely the header after some metadata
                if header_row_idx > 0 and max_fields > 1:
                    return pd.read_csv(filepath, header=header_row_idx)
                else:
                    return pd.read_csv(filepath)
                    
            except Exception:
                # Fallback to original method if file reading fails
                try:
                    return pd.read_csv(filepath)
                except pd.errors.ParserError:
                    # Last resort - skip bad lines
                    return pd.read_csv(filepath, on_bad_lines='skip')
                    
    elif filepath.lower().endswith(('.xlsx', '.xls')):
        # Handle Excel files - if first sheet is "Read Me", load second sheet
        xl = pd.ExcelFile(filepath)
        sheet_names = xl.sheet_names
        if sheet_names and sheet_names[0].strip().lower() == "read me":
            if len(sheet_names) > 1:
                return pd.read_excel(filepath, sheet_name=sheet_names[1])
            else:
                raise ValueError(f"Excel file {filepath} has only a 'Read Me' sheet and no data sheet.")
        else:
            return pd.read_excel(filepath, sheet_name=sheet_names[0])
    else:
        raise ValueError(f"Unsupported file type for: {filepath}")
