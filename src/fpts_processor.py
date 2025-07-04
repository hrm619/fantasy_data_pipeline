"""
FPTS Data Processor

Handles Value-Based Drafting (VBD) calculations for fantasy points data.
Includes position-specific baselines and QB adjustments.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional


def process_fpts_data(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Process FPTS data with VBD calculations.
    
    This function calculates Value-Based Drafting (VBD) scores by:
    1. Setting position-specific baselines
    2. Calculating VBD for each player
    3. Applying QB adjustment (50% reduction)
    4. Creating overall and positional rankings
    
    Args:
        df (pd.DataFrame): DataFrame containing FPTS data
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with VBD calculations
    """
    if verbose:
        print("📈 Processing FPTS data with VBD calculations...")
    
    # Position-specific baseline ranks (replacement level)
    baseline_dict = {'QB': 6, 'RB': 24, 'WR': 30, 'TE': 12}
    
    def calculate_vbd(row):
        """Calculate VBD for a single player row."""
        if pd.isna(row['FPTS']) or row['POS'] not in baseline_dict:
            return None
        
        pos = row['POS']
        baseline_rank = baseline_dict[pos]
        
        # Get all players of the same position, sorted by FPTS descending
        pos_players = df[df['POS'] == pos].sort_values('FPTS', ascending=False)
        
        if len(pos_players) >= baseline_rank:
            baseline_fpts = pos_players.iloc[baseline_rank - 1]['FPTS']
        else:
            baseline_fpts = 0
        
        return row['FPTS'] - baseline_fpts
    
    # Calculate VBD for each player
    df['VBD'] = df.apply(calculate_vbd, axis=1)
    
    # Apply QB adjustment (reduce VBD by 50%)
    qb_adjustment = 0.50
    df.loc[df['POS'] == 'QB', 'VBD'] *= qb_adjustment
    
    # Create overall and positional rankings
    df['RK'] = df['VBD'].rank(ascending=False, method='min')
    df['POS RANK'] = df.groupby('POS')['RK'].rank(method='min')
    
    if verbose:
        print("   ✓ VBD calculations completed")
        print("   Baseline players for each position:")
        for pos, baseline_rank in baseline_dict.items():
            pos_players = df[df['POS'] == pos].sort_values('FPTS', ascending=False)
            if len(pos_players) >= baseline_rank:
                baseline_player = pos_players.iloc[baseline_rank - 1]
                print(f"     {pos} Baseline (Rank {baseline_rank}): {baseline_player['PLAYER NAME']} - {baseline_player['FPTS']} FPTS")
    
    return df


def get_baseline_info(df: pd.DataFrame) -> Dict:
    """
    Get baseline player information for each position.
    
    Args:
        df (pd.DataFrame): DataFrame with FPTS data
        
    Returns:
        Dict: Dictionary containing baseline player info by position
    """
    baseline_dict = {'QB': 6, 'RB': 24, 'WR': 30, 'TE': 12}
    baseline_info = {}
    
    for pos, baseline_rank in baseline_dict.items():
        pos_players = df[df['POS'] == pos].sort_values('FPTS', ascending=False)
        if len(pos_players) >= baseline_rank:
            baseline_player = pos_players.iloc[baseline_rank - 1]
            baseline_info[pos] = {
                'rank': baseline_rank,
                'player': baseline_player['PLAYER NAME'],
                'fpts': baseline_player['FPTS']
            }
    
    return baseline_info 