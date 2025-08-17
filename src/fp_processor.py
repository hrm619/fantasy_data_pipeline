"""
FantasyPros Data Processor

Handles FantasyPros ranking data processing including position cleaning
and positional ranking calculations.
"""

import pandas as pd
import numpy as np


def process_fantasypros_data(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Process FantasyPros ranking data and return standardized columns.
    
    This function:
    1. Cleans position data by removing numbers
    2. Creates overall rank (RK) if not present using index
    3. Calculates positional rankings based on overall rank
    4. Returns standardized columns: PLAYER NAME, PLAYER ID, POS, TEAM, RK, POS RANK, TIER, ADP
    
    Args:
        df (pd.DataFrame): DataFrame containing FantasyPros data with columns:
                          PLAYER NAME, PLAYER ID, POS, TEAM, and optionally RK, TIER
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with standardized columns
    """
    if verbose:
        print("🔄 Processing FantasyPros data...")
    
    # Make a copy to avoid modifying original
    df_processed = df.copy()
    
    # Clean position data - remove numbers (e.g., "WR1" -> "WR")
    df_processed['POS'] = df_processed['POS'].str.replace(r'\d+', '', regex=True)
    
    # Handle ECR column (Expert Consensus Ranking) - if not present, use RK or create from index
    if 'ECR' not in df_processed.columns:
        if 'RK' in df_processed.columns:
            df_processed['ECR'] = df_processed['RK']
            if verbose:
                print("   ✓ Used RK column as ECR")
        else:
            df_processed['ECR'] = df_processed.index + 1
            if verbose:
                print("   ✓ Created ECR column using index values")
    
    # Ensure ECR is integer type
    df_processed['ECR'] = df_processed['ECR'].astype('Int64')
    
    # Calculate positional rankings based on ECR
    df_processed['POS ECR'] = df_processed.groupby('POS')['ECR'].rank(method='min').astype('Int64')
    
    # Define base required columns (always needed)
    base_required_columns = ['PLAYER NAME', 'PLAYER ID', 'POS', 'TEAM', 'POS ECR', 'ECR']
    
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
        print("   ✓ FantasyPros rankings processed")
        
        # Show position breakdown
        pos_counts = result_df['POS'].value_counts()
        print("   Position breakdown:")
        for pos, count in pos_counts.items():
            print(f"     {pos}: {count} players")
        
        print(f"   ✓ Returned {len(result_df)} players with standardized columns")
    
    return result_df


def get_position_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get summary statistics by position.
    
    Args:
        df (pd.DataFrame): DataFrame with FantasyPros data
        
    Returns:
        pd.DataFrame: Summary statistics by position
    """
    summary = df.groupby('POS').agg({
        'ECR': ['count', 'min', 'max', 'mean'],
        'POS ECR': ['max']
    }).round(2)
    
    summary.columns = ['Player Count', 'Min Rank', 'Max Rank', 'Avg Rank', 'Max Pos Rank']
    
    return summary 