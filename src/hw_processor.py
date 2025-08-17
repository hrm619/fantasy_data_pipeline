"""
HW Data Processor

Handles HW (tableDownload) ranking data processing including rank assignments
and positional ranking calculations.
"""

import pandas as pd
import numpy as np


def process_hw_data(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Process HW ranking data and return standardized columns.
    
    This function:
    1. Assigns overall rank based on order (index + 1) if not present
    2. Calculates positional rankings based on overall rank
    3. Returns standardized columns: PLAYER NAME, PLAYER ID, POS, TEAM, RK, POS RANK, TIER, ADP
    
    Args:
        df (pd.DataFrame): DataFrame containing HW ranking data with columns:
                          PLAYER NAME, PLAYER ID, POS, TEAM, and optionally RK, TIER, ADP
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with standardized columns
    """
    if verbose:
        print("🔄 Processing HW ranking data...")
    
    # Make a copy to avoid modifying original
    df_processed = df.copy()
    
    # Assign overall rank based on index (assuming data is pre-sorted) if not present
    if 'RK' not in df_processed.columns:
        df_processed['RK'] = df_processed.index + 1
        if verbose:
            print("   ✓ Created RK column using index values")
    
    # Ensure RK is integer type
    df_processed['RK'] = df_processed['RK'].astype('Int64')
    
    # Calculate positional rankings based on overall rank
    df_processed['POS RANK'] = df_processed.groupby('POS')['RK'].rank(method='min').astype('Int64')
    
    # Define base required columns (always needed)
    base_required_columns = ['PLAYER NAME', 'PLAYER ID', 'POS', 'TEAM', 'RK', 'POS RANK']
    
    # Define optional columns (only include if they exist)
    optional_columns = ['TIER', 'ADP', 'VBD']
    
    # Ensure all base required columns exist
    for col in base_required_columns:
        if col not in df_processed.columns:
            df_processed[col] = pd.NA
            if verbose:
                print(f"   ⚠ Added missing column: {col}")
    
    # Build final column list (base + available optional columns)
    final_columns = base_required_columns.copy()
    for col in optional_columns:
        if col in df_processed.columns:
            final_columns.append(col)
    
    # Select and return standardized columns
    result_df = df_processed[final_columns].copy()
    
    if verbose:
        print("   ✓ HW rankings processed")
        
        # Show ranking statistics
        print(f"   Total players ranked: {len(result_df)}")
        print(f"   Rank range: {result_df['RK'].min()} - {result_df['RK'].max()}")
        
        # Show position breakdown
        pos_summary = result_df.groupby('POS').agg({
            'RK': ['count', 'min', 'max'],
            'POS RANK': 'max'
        }).round(2)
        
        print("   Position breakdown:")
        for pos in pos_summary.index:
            count = pos_summary.loc[pos, ('RK', 'count')]
            min_rank = pos_summary.loc[pos, ('RK', 'min')]
            max_rank = pos_summary.loc[pos, ('RK', 'max')]
            print(f"     {pos}: {count} players (Ranks {min_rank}-{max_rank})")
        
        print(f"   ✓ Returned {len(result_df)} players with standardized columns")
    
    return result_df


def get_hw_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get ranking summary statistics by position.
    
    Args:
        df (pd.DataFrame): DataFrame with HW ranking data
        
    Returns:
        pd.DataFrame: Summary statistics by position
    """
    summary = df.groupby('POS').agg({
        'RK': ['count', 'min', 'max', 'mean'],
        'POS RANK': ['max']
    }).round(2)
    
    summary.columns = ['Player Count', 'Min Overall Rank', 'Max Overall Rank', 'Avg Overall Rank', 'Max Pos Rank']
    
    return summary


def validate_hw_rankings(df: pd.DataFrame) -> dict:
    """
    Validate HW ranking data for consistency.
    
    Args:
        df (pd.DataFrame): DataFrame with HW ranking data
        
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
