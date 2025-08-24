"""
Season Stats Processor

Calculates aggregated season statistics from historical fantasy football data
including total fantasy points, fantasy points per game, and position-specific
fantasy point breakdowns and percentages.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from .utils import validate_dataframe, safe_numeric_conversion, print_processing_summary


def calculate_season_stats(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Calculate season-long statistical aggregations from player total stats data.
    
    This function calculates:
    - Total fantasy points (FANTPT or similar)
    - Fantasy points per game (based on games played)
    - Rushing fantasy points and percentage
    - Receiving fantasy points and percentage  
    - Passing fantasy points and percentage
    - Touchdown fantasy points and percentage
    
    Args:
        df (pd.DataFrame): DataFrame containing season stats with columns like:
                          PLAYER NAME, POS, G, FANTPT, PASS TD, RUSH TD, REC TD, etc.
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with additional calculated fields:
                     - TOTAL_FPTS: Total fantasy points for the season
                     - FPTS_PER_GAME: Fantasy points per game played
                     - RUSH_FPTS: Fantasy points from rushing
                     - RUSH_FPTS_PCT: Percentage of fantasy points from rushing
                     - REC_FPTS: Fantasy points from receiving
                     - REC_FPTS_PCT: Percentage of fantasy points from receiving
                     - PASS_FPTS: Fantasy points from passing
                     - PASS_FPTS_PCT: Percentage of fantasy points from passing
                     - TD_FPTS: Fantasy points from touchdowns
                     - TD_FPTS_PCT: Percentage of fantasy points from touchdowns
    """
    if verbose:
        print("🔄 Processing season stats data...")
    
    # Make a copy to avoid modifying original
    df_processed = df.copy()
    
    # Validate basic required columns
    required_columns = ['PLAYER NAME', 'POS']
    if not validate_dataframe(df_processed, required_columns):
        raise ValueError("Missing required columns for season stats processing")
    
    # Calculate Half PPR fantasy points from component stats
    if verbose:
        print("   📊 Calculating Half PPR fantasy points from component stats...")
    
    # Define standard Half PPR scoring
    scoring_rules = {
        'PASS YDS': 0.04,    # 1 point per 25 passing yards
        'PASS TD': 4.0,      # 4 points per passing TD
        'PASS INT': -2.0,    # -2 points per interception
        'RUSH YDS': 0.1,     # 1 point per 10 rushing yards
        'RUSH TD': 6.0,      # 6 points per rushing TD
        'REC REC': 0.5,      # 0.5 points per reception (Half PPR)
        'REC YDS': 0.1,      # 1 point per 10 receiving yards
        'REC TD': 6.0,       # 6 points per receiving TD
        'FMB': -2.0,         # -2 points per fumble
        '2 PM': 2.0,         # 2 points per 2-point conversion
        '2 PP': 2.0          # 2 points per 2-point pass
    }
    
    # Initialize total fantasy points
    df_processed['TOTAL_FPTS'] = 0.0
    
    # Calculate points for each component that exists in the data
    for stat_col, points_per in scoring_rules.items():
        if stat_col in df_processed.columns:
            stat_value = safe_numeric_conversion(df_processed[stat_col])
            df_processed['TOTAL_FPTS'] += stat_value * points_per
            if verbose:
                print(f"   ✓ Added {stat_col}: {points_per} pts per unit")
        else:
            if verbose:
                print(f"   ⚠️  {stat_col} column not found, skipping")
    
    # Also check if there's an existing total fantasy points column to compare/use
    total_fpts_col = None
    possible_fpts_cols = ['FANTPT', 'FPTS', 'FANTASY_POINTS', 'PPR']
    for col in possible_fpts_cols:
        if col in df_processed.columns:
            total_fpts_col = col
            break
    
    if total_fpts_col is not None:
        existing_fpts = safe_numeric_conversion(df_processed[total_fpts_col])
        if verbose:
            calculated_avg = df_processed['TOTAL_FPTS'].mean()
            existing_avg = existing_fpts.mean()
            print(f"   📋 Calculated Half PPR avg: {calculated_avg:.2f}")
            print(f"   📋 Existing {total_fpts_col} avg: {existing_avg:.2f}")
            print(f"   ✓ Using calculated Half PPR fantasy points")
    else:
        if verbose:
            print(f"   ✓ Created Half PPR fantasy points from component stats")
    
    # Get games played (G column)
    if 'G' in df_processed.columns:
        df_processed['GAMES_PLAYED'] = safe_numeric_conversion(df_processed['G'], 'int')
    else:
        if verbose:
            print("   ⚠️  No games played column found, assuming 17 games")
        df_processed['GAMES_PLAYED'] = 17
    
    # Calculate fantasy points per game
    df_processed['FPTS_PER_GAME'] = np.where(
        df_processed['GAMES_PLAYED'] > 0,
        df_processed['TOTAL_FPTS'] / df_processed['GAMES_PLAYED'],
        0.0
    )
    
    # Calculate position-specific fantasy points
    _calculate_rushing_stats(df_processed, verbose)
    _calculate_receiving_stats(df_processed, verbose)
    _calculate_passing_stats(df_processed, verbose)
    _calculate_touchdown_stats(df_processed, verbose)
    
    # Calculate percentages
    _calculate_fantasy_point_percentages(df_processed, verbose)
    
    # Select final columns
    output_columns = [
        'PLAYER NAME', 'POS', 'TEAM', 'TOTAL_FPTS', 'FPTS_PER_GAME',
        'RUSH_FPTS', 'RUSH_FPTS_PCT', 'REC_FPTS', 'REC_FPTS_PCT',
        'PASS_FPTS', 'PASS_FPTS_PCT', 'TD_FPTS', 'TD_FPTS_PCT'
    ]
    
    # Only include columns that exist
    available_columns = [col for col in output_columns if col in df_processed.columns]
    result_df = df_processed[available_columns].copy()
    
    if verbose:
        print_processing_summary(result_df, "Season Stats")
        _print_stats_summary(result_df)
    
    return result_df


def _calculate_rushing_stats(df: pd.DataFrame, verbose: bool) -> None:
    """Calculate rushing fantasy points based on rushing yards and TDs."""
    # Standard scoring: 0.1 points per rushing yard, 6 points per rushing TD
    rush_yds = safe_numeric_conversion(df.get('RUSH YDS', pd.Series([0] * len(df))))
    rush_td = safe_numeric_conversion(df.get('RUSH TD', pd.Series([0] * len(df))))
    
    df['RUSH_FPTS'] = (rush_yds * 0.1) + (rush_td * 6.0)
    
    if verbose and any(col in df.columns for col in ['RUSH YDS', 'RUSH TD']):
        print("   ✓ Calculated rushing fantasy points")


def _calculate_receiving_stats(df: pd.DataFrame, verbose: bool) -> None:
    """Calculate receiving fantasy points based on receptions, yards, and TDs."""
    # Standard PPR scoring: 1 point per reception, 0.1 points per receiving yard, 6 points per receiving TD
    rec_rec = safe_numeric_conversion(df.get('REC REC', pd.Series([0] * len(df))))
    rec_yds = safe_numeric_conversion(df.get('REC YDS', pd.Series([0] * len(df))))
    rec_td = safe_numeric_conversion(df.get('REC TD', pd.Series([0] * len(df))))
    
    df['REC_FPTS'] = (rec_rec * 0.5) + (rec_yds * 0.1) + (rec_td * 6.0)
    
    if verbose and any(col in df.columns for col in ['REC REC', 'REC YDS', 'REC TD']):
        print("   ✓ Calculated receiving fantasy points")


def _calculate_passing_stats(df: pd.DataFrame, verbose: bool) -> None:
    """Calculate passing fantasy points based on passing yards and TDs."""
    # Standard scoring: 0.04 points per passing yard, 4 points per passing TD, -2 points per INT
    pass_yds = safe_numeric_conversion(df.get('PASS YDS', pd.Series([0] * len(df))))
    pass_td = safe_numeric_conversion(df.get('PASS TD', pd.Series([0] * len(df))))
    pass_int = safe_numeric_conversion(df.get('PASS INT', pd.Series([0] * len(df))))
    
    df['PASS_FPTS'] = (pass_yds * 0.04) + (pass_td * 4.0) - (pass_int * 2.0)
    
    if verbose and any(col in df.columns for col in ['PASS YDS', 'PASS TD', 'PASS INT']):
        print("   ✓ Calculated passing fantasy points")


def _calculate_touchdown_stats(df: pd.DataFrame, verbose: bool) -> None:
    """Calculate total touchdown fantasy points."""
    # Get all touchdown columns
    rush_td = safe_numeric_conversion(df.get('RUSH TD', pd.Series([0] * len(df))))
    rec_td = safe_numeric_conversion(df.get('REC TD', pd.Series([0] * len(df))))
    pass_td = safe_numeric_conversion(df.get('PASS TD', pd.Series([0] * len(df))))
    
    # Different point values for different types of TDs
    df['TD_FPTS'] = (rush_td * 6.0) + (rec_td * 6.0) + (pass_td * 4.0)
    
    if verbose:
        print("   ✓ Calculated touchdown fantasy points")


def _calculate_fantasy_point_percentages(df: pd.DataFrame, verbose: bool) -> None:
    """Calculate what percentage of total fantasy points come from each category."""
    # Avoid division by zero
    total_fpts_safe = np.where(df['TOTAL_FPTS'] > 0, df['TOTAL_FPTS'], 1.0)
    
    # Calculate percentages
    df['RUSH_FPTS_PCT'] = (df['RUSH_FPTS'] / total_fpts_safe * 100).round(1)
    df['REC_FPTS_PCT'] = (df['REC_FPTS'] / total_fpts_safe * 100).round(1)
    df['PASS_FPTS_PCT'] = (df['PASS_FPTS'] / total_fpts_safe * 100).round(1)
    df['TD_FPTS_PCT'] = (df['TD_FPTS'] / total_fpts_safe * 100).round(1)
    
    # Set percentages to 0 for players with 0 total fantasy points
    zero_fpts_mask = df['TOTAL_FPTS'] <= 0
    df.loc[zero_fpts_mask, ['RUSH_FPTS_PCT', 'REC_FPTS_PCT', 'PASS_FPTS_PCT', 'TD_FPTS_PCT']] = 0.0
    
    if verbose:
        print("   ✓ Calculated fantasy point percentages")


def _print_stats_summary(df: pd.DataFrame) -> None:
    """Print summary statistics for the processed data."""
    print(f"\n📈 Season Stats Summary:")
    
    if 'TOTAL_FPTS' in df.columns:
        print(f"   Total fantasy points range: {df['TOTAL_FPTS'].min():.1f} - {df['TOTAL_FPTS'].max():.1f}")
    
    if 'FPTS_PER_GAME' in df.columns:
        print(f"   Fantasy points per game range: {df['FPTS_PER_GAME'].min():.1f} - {df['FPTS_PER_GAME'].max():.1f}")
    
    # Show breakdown by position if available
    if 'POS' in df.columns:
        pos_stats = df.groupby('POS').agg({
            'TOTAL_FPTS': 'mean',
            'FPTS_PER_GAME': 'mean'
        }).round(1)
        print(f"   Average stats by position:")
        for pos, stats in pos_stats.iterrows():
            print(f"     {pos}: {stats['TOTAL_FPTS']:.1f} total FPTS, {stats['FPTS_PER_GAME']:.1f} FPTS/game")


def get_season_stats_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get summary statistics for season stats data by position.
    
    Args:
        df (pd.DataFrame): Processed season stats DataFrame
        
    Returns:
        pd.DataFrame: Summary statistics by position
    """
    if 'POS' not in df.columns:
        return pd.DataFrame()
    
    summary_stats = df.groupby('POS').agg({
        'TOTAL_FPTS': ['count', 'mean', 'median', 'std'],
        'FPTS_PER_GAME': ['mean', 'median', 'std'],
        'RUSH_FPTS_PCT': 'mean',
        'REC_FPTS_PCT': 'mean',
        'PASS_FPTS_PCT': 'mean',
        'TD_FPTS_PCT': 'mean'
    }).round(2)
    
    # Flatten column names
    summary_stats.columns = ['_'.join(col).strip() for col in summary_stats.columns.values]
    
    return summary_stats.reset_index()


def validate_season_stats(df: pd.DataFrame, verbose: bool = True) -> Dict[str, bool]:
    """
    Validate season stats calculations.
    
    Args:
        df (pd.DataFrame): Processed season stats DataFrame
        verbose (bool): Whether to print validation results
        
    Returns:
        Dict[str, bool]: Validation results for different checks
    """
    validation_results = {}
    
    # Check for negative fantasy points (should be rare but possible)
    validation_results['no_negative_total_fpts'] = not (df['TOTAL_FPTS'] < 0).any()
    
    # Check for reasonable fantasy points per game (should be < 50 for most players)
    validation_results['reasonable_fpts_per_game'] = not (df['FPTS_PER_GAME'] > 50).any()
    
    # Check that percentages sum to reasonable values (allowing for rounding and other scoring)
    if all(col in df.columns for col in ['RUSH_FPTS_PCT', 'REC_FPTS_PCT', 'PASS_FPTS_PCT']):
        total_pcts = df['RUSH_FPTS_PCT'] + df['REC_FPTS_PCT'] + df['PASS_FPTS_PCT']
        validation_results['reasonable_percentages'] = not (total_pcts > 150).any()  # Allow for other scoring
    
    if verbose:
        print(f"\n✅ Season Stats Validation:")
        for check, passed in validation_results.items():
            status = "✓" if passed else "❌"
            print(f"   {status} {check.replace('_', ' ').title()}: {'Passed' if passed else 'Failed'}")
    
    return validation_results
