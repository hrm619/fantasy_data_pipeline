"""
FantasyPros Data Processor

Handles FantasyPros ranking data processing including position cleaning
and positional ranking calculations.
"""

import pandas as pd
import numpy as np


def process_fantasypros_data(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Process FantasyPros ranking data.
    
    This function:
    1. Cleans position data by removing numbers
    2. Calculates positional rankings
    
    Args:
        df (pd.DataFrame): DataFrame containing FantasyPros data
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with cleaned positions and rankings
    """
    if verbose:
        print("🔄 Processing FantasyPros data...")
    
    # Clean position data - remove numbers (e.g., "WR1" -> "WR")
    df['POS'] = df['POS'].str.replace(r'\d+', '', regex=True)
    
    # Calculate positional rankings based on overall rank
    df['POS RANK'] = df.groupby('POS')['RK'].rank(method='min')
    
    if verbose:
        print("   ✓ FantasyPros rankings processed")
        
        # Show position breakdown
        pos_counts = df['POS'].value_counts()
        print("   Position breakdown:")
        for pos, count in pos_counts.items():
            print(f"     {pos}: {count} players")
    
    return df


def get_position_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get summary statistics by position.
    
    Args:
        df (pd.DataFrame): DataFrame with FantasyPros data
        
    Returns:
        pd.DataFrame: Summary statistics by position
    """
    summary = df.groupby('POS').agg({
        'RK': ['count', 'min', 'max', 'mean'],
        'POS RANK': ['max']
    }).round(2)
    
    summary.columns = ['Player Count', 'Min Rank', 'Max Rank', 'Avg Rank', 'Max Pos Rank']
    
    return summary 