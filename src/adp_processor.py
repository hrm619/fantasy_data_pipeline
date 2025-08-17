"""
FantasyPros ADP Data Processor

Handles FantasyPros ADP data processing including rank assignments
and positional ranking calculations.
"""

import pandas as pd
import numpy as np


def process_fantasypros_adp_data(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Process FantasyPros ADP data and return standardized columns.
    
    This function:
    1. Assigns overall rank based on order (index + 1) if not present
    2. Calculates positional rankings based on overall rank
    3. Returns standardized columns: PLAYER NAME, PLAYER ID, POS, TEAM, RK, POS RANK, TIER, ADP
    
    Args:
        df (pd.DataFrame): DataFrame containing FantasyPros ranking data with columns:
                          PLAYER NAME, PLAYER ID, POS, TEAM, and optionally RK, TIER
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with standardized columns
    """
    if verbose:
        print("🔄 Processing ADP data from FantasyPros...")
    
    # Make a copy to avoid modifying original
    df_processed = df.copy()
    
    # Define base required columns (always needed)
    base_required_columns = ['PLAYER NAME', 'PLAYER ID', 'POS', 'TEAM', 'ADP']
    
    # Ensure all base required columns exist
    for col in base_required_columns:   
        if col not in df_processed.columns:
            df_processed[col] = pd.NA
            if verbose:
                print(f"   ⚠ Added missing column: {col}")
    
    # Select and return standardized columns
    result_df = df_processed[base_required_columns].copy()


    # Process ADP data
    # Rename existing ADP column to preserve raw data
    if 'ADP' in df_processed.columns:
        # Create ADP ROUND column by dividing ADP by 12 and rounding up
        df_processed['ADP ROUND'] = np.ceil(df_processed['ADP'] / 12).astype('Int64')
        if verbose:
            print("   ✓ Created ADP ROUND column (12 picks per round)")
    
    # Ensure ADP is numeric type
    df_processed['ADP'] = df_processed['ADP'].astype('Int64')
    
    # Update base required columns to include ADP ROUND
    base_required_columns.append('ADP ROUND')
    
    # Update result_df to include the new column
    result_df = df_processed[base_required_columns].copy()

    
    if verbose:
        print("   ✓ ADP data from FantasyPros processed")
        
        # Show ranking statistics
        print(f"   Total players ranked: {len(result_df)}")
        print(f"   ADP range: {result_df['ADP'].min()} - {result_df['ADP'].max()}")
        
        # Show position breakdown
        pos_summary = result_df.groupby('POS').agg({
            'ADP': ['count', 'min', 'max']
        }).round(2)
        
        print("   ADP breakdown:")
        for pos in pos_summary.index:
            count = pos_summary.loc[pos, ('ADP', 'count')]
            min_adp = pos_summary.loc[pos, ('ADP', 'min')]
            max_adp = pos_summary.loc[pos, ('ADP', 'max')]
            print(f"     {pos}: {count} players (ADP {min_adp}-{max_adp})")
        
        print(f"   ✓ Returned {len(result_df)} players with standardized columns")
    
    return result_df


def get_adp_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get ADP summary statistics by position.
    
    Args:
        df (pd.DataFrame): DataFrame with ranking data
        
    Returns:
        pd.DataFrame: Summary statistics by position
    """
    summary = df.groupby('POS').agg({
        'ADP': ['count', 'min', 'max', 'mean']
    }).round(2)
    
    summary.columns = ['Player Count', 'Min ADP', 'Max ADP', 'Avg ADP']
    
    return summary


def validate_adp(df: pd.DataFrame) -> dict:
    """
    Validate ADP data for consistency.
    
    Args:
        df (pd.DataFrame): DataFrame with ranking data
        
    Returns:
        dict: Validation results
    """
    validation = {
        'total_players': len(df),
        'has_duplicates': df['ADP'].duplicated().any(),
        'has_missing_adp': df['ADP'].isna().any(),
        'adp_sequence_valid': (df['ADP'].sort_values().reset_index(drop=True) == range(1, len(df) + 1)).all(),
        'positions_covered': df['POS'].unique().tolist()
    }
    
    return validation 