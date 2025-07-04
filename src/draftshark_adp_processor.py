"""
DraftShark ADP Data Processor

Handles DraftShark Average Draft Position (ADP) data processing including
round calculations and pick assignments.
"""

import pandas as pd
import numpy as np


def process_draftshark_adp_data(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Process DraftShark ADP data.
    
    This function:
    1. Converts ADP to string format
    2. Calculates draft round from ADP
    3. Calculates round pick position
    4. Assigns ADP rank
    
    Args:
        df (pd.DataFrame): DataFrame containing DraftShark ADP data
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with ADP calculations
    """
    if verbose:
        print("🔄 Processing DraftShark ADP data...")
    
    # Convert ADP to string for processing
    df['SLEEPER ADP'] = df['SLEEPER ADP'].astype(str)
    
    # Extract round number from ADP (before decimal point)
    df['ADP ROUND'] = df['SLEEPER ADP'].str.split('.').str[0].astype(int)
    
    # Calculate pick position within round (assuming 12-team league)
    df['ADP ROUND PICK'] = ((df.index) % 12) + 1
    
    # Assign overall ADP rank
    df['ADP RANK'] = df.index + 1
    
    if verbose:
        print("   ✓ DraftShark ADP data processed")
        
        # Show ADP statistics
        print(f"   ADP Range: {df['ADP RANK'].min()} - {df['ADP RANK'].max()}")
        print(f"   Rounds: {df['ADP ROUND'].min()} - {df['ADP ROUND'].max()}")
        
        # Show round breakdown
        round_counts = df['ADP ROUND'].value_counts().sort_index()
        print("   Players by round:")
        for round_num, count in round_counts.head(5).items():
            print(f"     Round {round_num}: {count} players")
    
    return df


def get_adp_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get ADP summary statistics.
    
    Args:
        df (pd.DataFrame): DataFrame with ADP data
        
    Returns:
        pd.DataFrame: Summary statistics for ADP data
    """
    summary = df.groupby('ADP ROUND').agg({
        'ADP RANK': ['count', 'min', 'max'],
        'ADP ROUND PICK': ['min', 'max']
    }).round(2)
    
    summary.columns = ['Players', 'Min ADP Rank', 'Max ADP Rank', 'Min Round Pick', 'Max Round Pick']
    
    return summary


def calculate_adp_round_pick(adp_rank: int, league_size: int = 12) -> tuple:
    """
    Calculate round and pick from ADP rank.
    
    Args:
        adp_rank (int): Overall ADP rank
        league_size (int): Number of teams in league
        
    Returns:
        tuple: (round_number, pick_in_round)
    """
    round_number = ((adp_rank - 1) // league_size) + 1
    pick_in_round = ((adp_rank - 1) % league_size) + 1
    
    return round_number, pick_in_round 