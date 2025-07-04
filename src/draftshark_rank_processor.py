"""
DraftShark Rank Data Processor

Handles DraftShark ranking data processing including rank assignments
and positional ranking calculations.
"""

import pandas as pd
import numpy as np


def process_draftshark_rank_data(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Process DraftShark ranking data.
    
    This function:
    1. Assigns overall rank based on order
    2. Calculates positional rankings
    
    Args:
        df (pd.DataFrame): DataFrame containing DraftShark ranking data
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with rank assignments
    """
    if verbose:
        print("🔄 Processing DraftShark ranking data...")
    
    # Assign overall rank based on index (assuming data is pre-sorted)
    df['RK'] = df.index + 1
    
    # Calculate positional rankings
    df['POS RANK'] = df.groupby('POS')['RK'].rank(method='min')
    
    if verbose:
        print("   ✓ DraftShark rankings processed")
        
        # Show ranking statistics
        print(f"   Total players ranked: {len(df)}")
        print(f"   Rank range: {df['RK'].min()} - {df['RK'].max()}")
        
        # Show position breakdown
        pos_summary = df.groupby('POS').agg({
            'RK': ['count', 'min', 'max'],
            'POS RANK': 'max'
        }).round(2)
        
        print("   Position breakdown:")
        for pos in pos_summary.index:
            count = pos_summary.loc[pos, ('RK', 'count')]
            min_rank = pos_summary.loc[pos, ('RK', 'min')]
            max_rank = pos_summary.loc[pos, ('RK', 'max')]
            print(f"     {pos}: {count} players (Ranks {min_rank}-{max_rank})")
    
    return df


def get_ranking_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get ranking summary statistics by position.
    
    Args:
        df (pd.DataFrame): DataFrame with ranking data
        
    Returns:
        pd.DataFrame: Summary statistics by position
    """
    summary = df.groupby('POS').agg({
        'RK': ['count', 'min', 'max', 'mean'],
        'POS RANK': ['max']
    }).round(2)
    
    summary.columns = ['Player Count', 'Min Overall Rank', 'Max Overall Rank', 'Avg Overall Rank', 'Max Pos Rank']
    
    return summary


def validate_rankings(df: pd.DataFrame) -> dict:
    """
    Validate ranking data for consistency.
    
    Args:
        df (pd.DataFrame): DataFrame with ranking data
        
    Returns:
        dict: Validation results
    """
    validation = {
        'total_players': len(df),
        'has_duplicates': df['RK'].duplicated().any(),
        'has_missing_ranks': df['RK'].isna().any(),
        'rank_sequence_valid': (df['RK'].sort_values().reset_index(drop=True) == range(1, len(df) + 1)).all(),
        'positions_covered': df['POS'].unique().tolist()
    }
    
    return validation 