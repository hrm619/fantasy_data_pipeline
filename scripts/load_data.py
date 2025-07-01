# Import required dependencies for data loading and processing

import sys
import os
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath("")))

# loads data from csv or excel files
def load_data(filepath):
    """
    Loads a file into a pandas DataFrame based on its extension.
    Supports CSV and Excel (xlsx) files.

    Args:
        filepath (str): Path to the file.

    Returns:
        pd.DataFrame: Loaded data.

    Raises:
        ValueError: If the file extension is not supported.
    """
    # Explain: Check file extension and use appropriate pandas reader
    if filepath.lower().endswith('.csv'):
        return pd.read_csv(filepath)
    elif filepath.lower().endswith(('.xlsx', '.xls')):
        # Explain: If the first sheet is named "Read Me", load the second sheet; otherwise, load the first.
        xl = pd.ExcelFile(filepath)
        sheet_names = xl.sheet_names
        if sheet_names and sheet_names[0].strip().lower() == "read me":
            # Load the second sheet if it exists
            if len(sheet_names) > 1:
                return pd.read_excel(filepath, sheet_name=sheet_names[1])
            else:
                raise ValueError(f"Excel file {filepath} has only a 'Read Me' sheet and no data sheet.")
        else:
            return pd.read_excel(filepath, sheet_name=sheet_names[0])
    else:
        raise ValueError(f"Unsupported file type for: {filepath}")
