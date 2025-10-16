"""
Utility functions for data processing.

Simple implementations of the utility functions needed by season_stats_processor.py 
and weekly_stats_processor.py.
"""

import pandas as pd
import numpy as np
from typing import List, Union, Optional, Any


def validate_dataframe(df: pd.DataFrame, required_columns: List[str]) -> bool:
    """
    Validate that a DataFrame contains all required columns.
    
    Args:
        df (pd.DataFrame): DataFrame to validate
        required_columns (List[str]): List of required column names
        
    Returns:
        bool: True if all columns are present, False otherwise
    """
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Warning: Missing required columns: {missing_columns}")
        return False
    return True


def safe_numeric_conversion(series: Union[pd.Series, Any], dtype: str = 'float') -> pd.Series:
    """
    Safely convert a pandas Series to numeric type.
    
    Args:
        series (Union[pd.Series, Any]): Data to convert
        dtype (str): Target numeric type ('float' or 'int')
        
    Returns:
        pd.Series: Converted series with numeric values
    """
    if not isinstance(series, pd.Series):
        if isinstance(series, (list, tuple)):
            series = pd.Series(series)
        else:
            return pd.Series([series])
    
    try:
        if dtype == 'int':
            return pd.to_numeric(series, errors='coerce').fillna(0).astype('Int64')
        else:
            return pd.to_numeric(series, errors='coerce').fillna(0.0)
    except Exception:
        # Fallback to zeros if conversion fails
        if dtype == 'int':
            return pd.Series([0] * len(series), dtype='Int64')
        else:
            return pd.Series([0.0] * len(series))


def print_processing_summary(df: pd.DataFrame, process_name: str):
    """
    Print a summary of the processed DataFrame.
    
    Args:
        df (pd.DataFrame): Processed DataFrame
        process_name (str): Name of the processing step
    """
    print(f"   ✓ {process_name} processing completed")
    print(f"   Total records: {len(df)}")
    
    if 'POS' in df.columns:
        pos_counts = df['POS'].value_counts()
        print("   Position breakdown:")
        for pos, count in pos_counts.items():
            print(f"     {pos}: {count} players")
    
    print(f"   Columns: {len(df.columns)}")
