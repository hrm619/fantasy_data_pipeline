"""
Utility functions for fantasy football data processing.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional


def validate_dataframe(df: pd.DataFrame, required_columns: List[str]) -> bool:
    """
    Validate that a DataFrame has the required columns.
    
    Args:
        df (pd.DataFrame): DataFrame to validate
        required_columns (List[str]): List of required column names
        
    Returns:
        bool: True if all required columns are present
    """
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        print(f"   ❌ Missing required columns: {missing_columns}")
        return False
    
    return True


def clean_player_names(df: pd.DataFrame, column_name: str = 'PLAYER NAME') -> pd.DataFrame:
    """
    Clean player names by removing special characters.
    
    Args:
        df (pd.DataFrame): DataFrame containing player names
        column_name (str): Name of the column containing player names
        
    Returns:
        pd.DataFrame: DataFrame with cleaned player names
    """
    if column_name in df.columns:
        df[column_name] = df[column_name].str.replace(r'[^\w\s]', '', regex=True)
    
    return df


def get_position_breakdown(df: pd.DataFrame, pos_column: str = 'POS') -> pd.DataFrame:
    """
    Get a breakdown of players by position.
    
    Args:
        df (pd.DataFrame): DataFrame containing position data
        pos_column (str): Name of the position column
        
    Returns:
        pd.DataFrame: Summary of players by position
    """
    if pos_column not in df.columns:
        return pd.DataFrame()
    
    breakdown = df[pos_column].value_counts().sort_index()
    
    return pd.DataFrame({
        'Position': breakdown.index,
        'Count': breakdown.values
    })


def filter_main_positions(df: pd.DataFrame, pos_column: str = 'POS') -> pd.DataFrame:
    """
    Filter DataFrame to only include main fantasy positions.
    
    Args:
        df (pd.DataFrame): DataFrame to filter
        pos_column (str): Name of the position column
        
    Returns:
        pd.DataFrame: Filtered DataFrame
    """
    main_positions = ['QB', 'RB', 'WR', 'TE']
    
    if pos_column in df.columns:
        return df[df[pos_column].isin(main_positions)]
    
    return df


def calculate_match_rate(df: pd.DataFrame, column_name: str) -> float:
    """
    Calculate the match rate for a column (non-null values).
    
    Args:
        df (pd.DataFrame): DataFrame to analyze
        column_name (str): Name of the column to check
        
    Returns:
        float: Match rate as percentage
    """
    if column_name not in df.columns:
        return 0.0
    
    total = len(df)
    matched = df[column_name].notna().sum()
    
    return (matched / total * 100) if total > 0 else 0.0


def print_processing_summary(df: pd.DataFrame, source_name: str):
    """
    Print a summary of processed data.
    
    Args:
        df (pd.DataFrame): Processed DataFrame
        source_name (str): Name of the data source
    """
    print(f"\n📊 {source_name} Processing Summary:")
    print(f"   Total rows: {len(df)}")
    print(f"   Total columns: {len(df.columns)}")
    
    if 'POS' in df.columns:
        pos_breakdown = get_position_breakdown(df)
        print("   Position breakdown:")
        for _, row in pos_breakdown.iterrows():
            print(f"     {row['Position']}: {row['Count']} players")
    
    if 'RK' in df.columns:
        print(f"   Rank range: {df['RK'].min()} - {df['RK'].max()}")
    
    print("   ✓ Processing completed successfully")


def safe_numeric_conversion(series: pd.Series, target_type: str = 'float') -> pd.Series:
    """
    Safely convert a series to numeric type.
    
    Args:
        series (pd.Series): Series to convert
        target_type (str): Target type ('float' or 'int')
        
    Returns:
        pd.Series: Converted series
    """
    try:
        if target_type == 'int':
            return pd.to_numeric(series, errors='coerce').astype('Int64')
        else:
            return pd.to_numeric(series, errors='coerce')
    except Exception as e:
        print(f"   ⚠️  Warning: Could not convert series to {target_type}: {e}")
        return series 