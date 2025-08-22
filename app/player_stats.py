"""
Player Stats Aggregator

Combines historical season and weekly statistics for player rankings analysis.
This module provides functions to aggregate both season-long totals and weekly trends
that can be merged into the rankings pipeline.
"""

import pandas as pd
import numpy as np
import sys
import os
from typing import Dict, Optional, Tuple
from datetime import datetime

# Add src directory to path for imports
src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from season_stats_processor import calculate_season_stats, get_season_stats_summary, validate_season_stats
    from weekly_stats_processor import calculate_weekly_trends, get_weekly_trends_summary, validate_weekly_trends, compare_half_season_performance
except ImportError:
    # Fallback for different import paths
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
    from season_stats_processor import calculate_season_stats, get_season_stats_summary, validate_season_stats
    from weekly_stats_processor import calculate_weekly_trends, get_weekly_trends_summary, validate_weekly_trends, compare_half_season_performance


def aggregate_player_historical_stats(
    season_data_path: str,
    weekly_data_path: str,
    player_key_path: str = "player_key_dict.json",
    season_filter: Optional[int] = 2024,
    output_dir: Optional[str] = None,
    outlier_method: str = 'percentile',
    outlier_percentile: float = 10.0,
    outlier_n_games: int = 2,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Aggregate historical player statistics from both season totals and weekly data.
    
    This function:
    1. Loads season total stats and calculates fantasy point breakdowns
    2. Filters season data to specified season (default: 2024)
    3. Loads weekly stats and calculates trend metrics
    4. Merges the data together for comprehensive player analysis
    5. Returns combined dataset ready for integration with rankings
    
    Args:
        season_data_path (str): Path to season totals CSV file
        weekly_data_path (str): Path to weekly fantasy points CSV file  
        player_key_path (str): Path to player key dictionary for ID mapping
        season_filter (Optional[int]): Season to filter to (default: 2024, None for all seasons)
        output_dir (Optional[str]): Directory to save output CSV file (if None, no file saved)
        outlier_method (str): Method for removing outliers from weekly averages
        outlier_percentile (float): Percentile threshold for outlier removal
        outlier_n_games (int): Number of highest/lowest games to remove
        verbose (bool): Whether to print detailed progress information
        
    Returns:
        pd.DataFrame: Combined DataFrame with season and weekly stats including:
                     - PLAYER_ID, PLAYER_NAME, POS, TEAM
                     - Season stats: TOTAL_FPTS, FPTS_PER_GAME, rush/rec/pass breakdowns
                     - Weekly trends: FIRST_HALF_AVG, SECOND_HALF_AVG, AVG_NO_OUTLIERS
                     - Consistency metrics: CONSISTENCY_SCORE, COEFFICIENT_OF_VARIATION
    """
    if verbose:
        print("🏈 Starting player historical stats aggregation...")
        print(f"   Season data: {season_data_path}")
        print(f"   Weekly data: {weekly_data_path}")
        if season_filter:
            print(f"   Season filter: {season_filter}")
    
    # Load season data
    if verbose:
        print("\n📊 Step 1: Loading and processing season stats...")
    
    try:
        season_df = pd.read_csv(season_data_path)
        if verbose:
            print(f"   ✓ Loaded season data: {len(season_df)} players (all seasons)")
    except Exception as e:
        raise FileNotFoundError(f"Could not load season data from {season_data_path}: {e}")
    
    # Filter to specific season if requested
    if season_filter is not None:
        if 'SEASON' in season_df.columns:
            initial_count = len(season_df)
            season_df = season_df[season_df['SEASON'] == season_filter]
            filtered_count = len(season_df)
            if verbose:
                print(f"   ✓ Filtered to {season_filter} season: {filtered_count} players (from {initial_count} total)")
            if filtered_count == 0:
                raise ValueError(f"No data found for season {season_filter}")
        else:
            if verbose:
                print(f"   ⚠️  No SEASON column found, using all data")
    
    # Process season statistics
    season_stats = calculate_season_stats(season_df, verbose=verbose)
    
    # Load weekly data
    if verbose:
        print("\n📈 Step 2: Loading and processing weekly stats...")
    
    try:
        weekly_df = pd.read_csv(weekly_data_path)
        if verbose:
            print(f"   ✓ Loaded weekly data: {len(weekly_df)} players")
    except Exception as e:
        raise FileNotFoundError(f"Could not load weekly data from {weekly_data_path}: {e}")
    
    # Process weekly trends
    weekly_trends = calculate_weekly_trends(
        weekly_df,
        outlier_method=outlier_method,
        outlier_percentile=outlier_percentile,
        outlier_n_games=outlier_n_games,
        verbose=verbose
    )
    
    # Load player key dictionary for standardized IDs
    player_key_dict = {}
    if os.path.exists(player_key_path):
        import json
        try:
            with open(player_key_path, 'r') as f:
                player_key_dict = json.load(f)
            if verbose:
                print(f"\n🔑 Loaded player key dictionary: {len(player_key_dict)} players")
        except Exception as e:
            if verbose:
                print(f"   ⚠️  Could not load player key dictionary: {e}")
    
    # Add player IDs to both datasets before merging for better matching
    if player_key_dict:
        if verbose:
            print("\n🔑 Step 3: Adding player IDs for improved matching...")
        season_stats = _add_player_ids(season_stats, player_key_dict, verbose)
        weekly_trends = _add_player_ids(weekly_trends, player_key_dict, verbose)
    
    # Merge season and weekly data
    if verbose:
        print("\n🔗 Step 4: Merging season and weekly statistics...")
    
    merged_df = _merge_season_and_weekly_data(season_stats, weekly_trends, player_key_dict, verbose)
    
    # Validate final results
    if verbose:
        print("\n✅ Step 5: Validating aggregated data...")
        _validate_aggregated_data(merged_df, verbose)
    
    if verbose:
        print(f"\n🎯 Aggregation complete! Final dataset: {len(merged_df)} players with combined stats")
        _print_aggregation_summary(merged_df)
    
    # Save to file if output directory specified
    if output_dir is not None:
        saved_path = save_historical_stats(merged_df, output_dir, "aggregated_historical_stats", verbose)
        if verbose:
            print(f"\n💾 Historical stats saved to: {saved_path}")
    
    return merged_df


def _merge_season_and_weekly_data(season_df: pd.DataFrame, weekly_df: pd.DataFrame,
                                 player_key_dict: Dict, verbose: bool) -> pd.DataFrame:
    """Merge season and weekly statistics DataFrames using player IDs when available."""
    
    # Standardize weekly column names to match expected output
    weekly_df_clean = weekly_df.copy()
    column_mapping = {
        '1H_PPG': 'FIRST_HALF_AVG',
        '2H_PPG': 'SECOND_HALF_AVG', 
        'NO_OUTLIERS_PPG': 'AVG_NO_OUTLIERS',
        'STD_DEV': 'CONSISTENCY_SCORE',
        'CV': 'COEFFICIENT_OF_VARIATION'
    }
    weekly_df_clean = weekly_df_clean.rename(columns=column_mapping)
    
    # Try to merge on PLAYER_ID first (most reliable)
    if 'PLAYER_ID' in season_df.columns and 'PLAYER_ID' in weekly_df_clean.columns:
        if verbose:
            print("   🎯 Merging using Player IDs (most reliable)")
        
        merged_df = season_df.merge(
            weekly_df_clean, 
            on='PLAYER_ID', 
            how='left'
        )
        
        # Calculate match statistics
        player_id_matches = merged_df['PLAYER_ID'].notna().sum()
        weekly_data_matches = merged_df['FIRST_HALF_AVG'].notna().sum()
        
    else:
        # Fallback to name matching
        if verbose:
            print("   📝 Falling back to name-based matching")
            
        # Standardize player name columns for merging
        season_merge_col = 'PLAYER NAME' if 'PLAYER NAME' in season_df.columns else 'Player'
        weekly_merge_col = 'PLAYER NAME' if 'PLAYER NAME' in weekly_df_clean.columns else 'Player'
        
        if season_merge_col not in season_df.columns or weekly_merge_col not in weekly_df_clean.columns:
            if verbose:
                print("   ⚠️  Missing player name columns for merging, returning season data only")
            # If we can't merge properly, just return season data with NaN weekly columns
            result_df = season_df.copy()
            # Add placeholder weekly columns
            weekly_cols = ['FIRST_HALF_AVG', 'SECOND_HALF_AVG', 'AVG_NO_OUTLIERS', 
                          'CONSISTENCY_SCORE', 'COEFFICIENT_OF_VARIATION']
            for col in weekly_cols:
                result_df[col] = np.nan
            return result_df
        
        # Clean player names for better matching
        season_df[season_merge_col] = season_df[season_merge_col].str.strip()
        weekly_df_clean[weekly_merge_col] = weekly_df_clean[weekly_merge_col].str.strip()
        
        # Perform merge
        merged_df = season_df.merge(
            weekly_df_clean, 
            left_on=season_merge_col, 
            right_on=weekly_merge_col, 
            how='left'
        )
        
        # Calculate match statistics  
        weekly_data_matches = merged_df['FIRST_HALF_AVG'].notna().sum()
    
    # Clean up column names to avoid _x/_y suffixes from merging
    # Prioritize season data for shared columns like POS, TEAM
    columns_to_clean = ['POS', 'TEAM', 'PLAYER NAME']
    for col in columns_to_clean:
        if f'{col}_x' in merged_df.columns and f'{col}_y' in merged_df.columns:
            # Use season data (_x) and drop weekly data (_y)
            merged_df[col] = merged_df[f'{col}_x']
            merged_df = merged_df.drop(columns=[f'{col}_x', f'{col}_y'])
        elif f'{col}_x' in merged_df.columns:
            merged_df[col] = merged_df[f'{col}_x']
            merged_df = merged_df.drop(columns=[f'{col}_x'])
        elif f'{col}_y' in merged_df.columns:
            merged_df[col] = merged_df[f'{col}_y']
            merged_df = merged_df.drop(columns=[f'{col}_y'])
    
    # Round floating point numbers to avoid precision issues
    float_columns = merged_df.select_dtypes(include=[np.number]).columns
    for col in float_columns:
        merged_df[col] = merged_df[col].round(2)
    
    if verbose:
        season_count = len(season_df)
        weekly_count = len(weekly_df_clean)
        merged_count = len(merged_df)
        
        # Check for weekly data columns to calculate match rate
        weekly_indicator_cols = ['FIRST_HALF_AVG', 'SECOND_HALF_AVG', 'AVG_NO_OUTLIERS']
        weekly_col_found = None
        for col in weekly_indicator_cols:
            if col in merged_df.columns:
                weekly_col_found = col
                break
        
        if weekly_col_found:
            match_count = merged_df[weekly_col_found].notna().sum()
        else:
            match_count = 0
        match_rate = (match_count / season_count * 100) if season_count > 0 else 0
        
        print(f"   ✓ Merged {season_count} season + {weekly_count} weekly records")
        print(f"   ✓ {match_count}/{season_count} players have weekly data ({match_rate:.1f}%)")
    
    return merged_df


def _standardize_player_name(name: str) -> str:
    """
    Standardize player names to improve matching with player key dictionary.
    
    Common transformations:
    - Remove periods from initials (C.J. -> CJ)
    - Remove apostrophes (D'Andre -> DAndre)
    - Remove Jr./Sr./III suffixes
    - Standardize hyphenated names
    """
    if pd.isna(name):
        return name
    
    # Start with the original name
    standardized = str(name).strip()
    
    # Remove common suffixes that might not be in player key
    suffixes_to_remove = [' Jr.', ' Sr.', ' III', ' II', ' IV']
    for suffix in suffixes_to_remove:
        if standardized.endswith(suffix):
            standardized = standardized[:-len(suffix)]
            break
    
    # Remove periods from initials (C.J. Stroud -> CJ Stroud)
    standardized = standardized.replace('.', '')
    
    # Remove apostrophes (D'Andre Swift -> DAndre Swift)
    standardized = standardized.replace("'", '')
    
    return standardized


def _generate_name_variations(name: str) -> list:
    """
    Generate multiple variations of a player name for better matching.
    
    Returns a list of possible name variations including:
    - Original name
    - Standardized name
    - Hyphen removed versions
    - Different hyphen/space combinations
    """
    if pd.isna(name):
        return [name]
    
    variations = []
    original = str(name).strip()
    variations.append(original)
    
    # Add standardized version
    standardized = _standardize_player_name(original)
    variations.append(standardized)
    
    # For hyphenated names, try different combinations
    if '-' in original:
        # Remove all hyphens: "Amon-Ra St. Brown" -> "AmonRa St. Brown"
        no_hyphens = original.replace('-', '')
        variations.append(no_hyphens)
        variations.append(_standardize_player_name(no_hyphens))
        
        # Replace hyphens with spaces: "Smith-Njigba" -> "Smith Njigba"
        space_version = original.replace('-', ' ')
        variations.append(space_version)
        variations.append(_standardize_player_name(space_version))
        
        # For compound last names: "Jaxon Smith-Njigba" -> "Jaxon SmithNjigba"
        if ' ' in original:
            parts = original.split(' ')
            if len(parts) >= 2 and '-' in parts[-1]:
                # Last part has hyphen, combine it: "Smith-Njigba" -> "SmithNjigba"
                new_parts = parts[:-1] + [parts[-1].replace('-', '')]
                combined_version = ' '.join(new_parts)
                variations.append(combined_version)
                variations.append(_standardize_player_name(combined_version))
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for var in variations:
        if var not in seen:
            seen.add(var)
            unique_variations.append(var)
    
    return unique_variations


def _add_player_ids(df: pd.DataFrame, player_key_dict: Dict, verbose: bool) -> pd.DataFrame:
    """Add standardized player IDs to the DataFrame with enhanced name matching."""
    # Find the player name column
    name_col = None
    for col in ['PLAYER NAME', 'Player', 'PLAYER_NAME']:
        if col in df.columns:
            name_col = col
            break
    
    if name_col is None:
        if verbose:
            print("   ⚠️  No player name column found for ID mapping")
        return df
    
    # Create comprehensive reverse mapping (name to ID) with all variations
    # The player_key_dict has format: {player_id: [list_of_names]}
    name_to_id = {}
    for player_id, names in player_key_dict.items():
        if isinstance(names, list):
            name_list = names
        else:
            name_list = [names]
        
        for name in name_list:
            # Generate all variations for each name in the player key
            variations = _generate_name_variations(name.strip())
            for variation in variations:
                name_to_id[variation] = player_id
    
    # Function to find best match for a player name
    def find_best_match(player_name):
        if pd.isna(player_name):
            return None
        
        # Try direct lookup first
        if player_name in name_to_id:
            return name_to_id[player_name]
        
        # Try all variations of the player name
        variations = _generate_name_variations(player_name)
        for variation in variations:
            if variation in name_to_id:
                return name_to_id[variation]
        
        return None
    
    # Apply the enhanced matching
    df['PLAYER_ID'] = df[name_col].apply(find_best_match)
    
    # Calculate match rate
    total_players = len(df)
    matched_players = df['PLAYER_ID'].notna().sum()
    match_rate = (matched_players / total_players * 100) if total_players > 0 else 0
    
    if verbose:
        print(f"   ✓ Added player IDs: {matched_players}/{total_players} matched ({match_rate:.1f}%)")
        
        # Show details about remaining unmatched players by position
        if matched_players < total_players:
            unmatched_count = total_players - matched_players
            unmatched_df = df[df['PLAYER_ID'].isna()]
            
            if 'POS' in unmatched_df.columns:
                pos_breakdown = unmatched_df['POS'].value_counts()
                skill_positions = pos_breakdown.drop(['DST', 'K'], errors='ignore').sum()
                dst_k_positions = pos_breakdown.get('DST', 0) + pos_breakdown.get('K', 0)
                
                print(f"   ℹ️  {unmatched_count} players still unmatched: {skill_positions} skill players, {dst_k_positions} DST/K")
            else:
                print(f"   ℹ️  {unmatched_count} players still unmatched after enhanced name matching")
    
    return df


def _validate_aggregated_data(df: pd.DataFrame, verbose: bool) -> None:
    """Validate the aggregated dataset."""
    validation_issues = []
    warnings = []
    
    # Check for basic data integrity
    if len(df) == 0:
        validation_issues.append("Empty dataset")
    
    # Check for reasonable fantasy point values
    if 'TOTAL_FPTS' in df.columns:
        # Negative fantasy points can be valid (due to fumbles, INTs, etc.) but flag if excessive
        negative_count = (df['TOTAL_FPTS'] < -10).sum()
        if negative_count > 0:
            warnings.append(f"{negative_count} players with fantasy points < -10 (likely due to fumbles/turnovers)")
        
        if (df['TOTAL_FPTS'] > 500).any():
            validation_issues.append("Unreasonably high fantasy points (>500) found")
    
    # Check weekly averages are reasonable
    weekly_cols = ['FIRST_HALF_AVG', 'SECOND_HALF_AVG', 'AVG_NO_OUTLIERS']
    for col in weekly_cols:
        if col in df.columns:
            negative_weekly = (df[col] < -5).sum()  # Allow some negative but flag excessive
            if negative_weekly > 0:
                warnings.append(f"{negative_weekly} players with {col} < -5")
            if (df[col] > 60).any():
                validation_issues.append(f"Unreasonably high values in {col} (>60)")
    
    # Check data completeness
    if 'FIRST_HALF_AVG' in df.columns:
        weekly_data_completeness = (df['FIRST_HALF_AVG'].notna().sum() / len(df) * 100)
        if weekly_data_completeness < 50:
            warnings.append(f"Low weekly data completeness: {weekly_data_completeness:.1f}%")
    
    if validation_issues:
        if verbose:
            print("   ❌ Validation issues found:")
            for issue in validation_issues:
                print(f"      - {issue}")
    
    if warnings:
        if verbose:
            print("   ⚠️  Validation warnings:")
            for warning in warnings:
                print(f"      - {warning}")
    
    if not validation_issues and not warnings:
        if verbose:
            print("   ✓ Data validation passed")


def _print_aggregation_summary(df: pd.DataFrame) -> None:
    """Print summary statistics for the aggregated dataset."""
    print(f"\n📋 Aggregated Data Summary:")
    print(f"   Total players: {len(df)}")
    
    if 'POS' in df.columns:
        pos_counts = df['POS'].value_counts()
        print(f"   Position breakdown:")
        for pos, count in pos_counts.items():
            print(f"     {pos}: {count} players")
    
    # Summary of key metrics
    if 'TOTAL_FPTS' in df.columns:
        avg_fpts = df['TOTAL_FPTS'].mean()
        print(f"   Average total fantasy points: {avg_fpts:.1f}")
    
    if 'FIRST_HALF_AVG' in df.columns and 'SECOND_HALF_AVG' in df.columns:
        first_half = df['FIRST_HALF_AVG'].mean()
        second_half = df['SECOND_HALF_AVG'].mean()
        print(f"   Average weekly scores: 1H={first_half:.1f}, 2H={second_half:.1f}")
    
    # Data completeness
    if 'PLAYER_ID' in df.columns:
        id_completeness = (df['PLAYER_ID'].notna().sum() / len(df) * 100)
        print(f"   Player ID completeness: {id_completeness:.1f}%")


def save_historical_stats(df: pd.DataFrame, 
                         output_dir: str, 
                         filename_prefix: str = "historical_stats",
                         verbose: bool = True) -> str:
    """
    Save historical stats DataFrame to CSV with timestamped filename.
    
    Args:
        df (pd.DataFrame): DataFrame to save
        output_dir (str): Directory to save the file
        filename_prefix (str): Prefix for the filename
        verbose (bool): Whether to print save information
        
    Returns:
        str: Path to the saved file
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate timestamped filename
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y%m%d_%H%M")
    filename = f'{filename_prefix}_{timestamp}.csv'
    output_path = os.path.join(output_dir, filename)
    
    # Save to CSV
    df.to_csv(output_path, index=False)
    
    if verbose:
        print(f"   ✓ Data saved to: {output_path}")
        print(f"   ✓ Dataset contains {len(df)} players with {len(df.columns)} columns")
    
    return output_path


def create_rankings_ready_dataset(aggregated_df: pd.DataFrame, 
                                current_season: str = "2024",
                                min_games: int = 8,
                                output_dir: Optional[str] = None,
                                verbose: bool = True) -> pd.DataFrame:
    """
    Create a rankings-ready dataset from aggregated historical stats.
    
    This function filters and formats the aggregated data to be ready for
    integration with the current rankings pipeline.
    
    Args:
        aggregated_df (pd.DataFrame): Output from aggregate_player_historical_stats
        current_season (str): Season identifier for filtering
        min_games (int): Minimum games played to include player
        output_dir (Optional[str]): Directory to save output CSV file (if None, no file saved)
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Rankings-ready dataset with standardized columns
    """
    if verbose:
        print("🎯 Creating rankings-ready dataset...")
    
    # Make a copy
    df = aggregated_df.copy()
    
    # Filter by minimum games if TOTAL_GAMES column exists
    if 'TOTAL_GAMES' in df.columns:
        initial_count = len(df)
        df = df[df['TOTAL_GAMES'] >= min_games]
        filtered_count = len(df)
        if verbose:
            print(f"   ✓ Filtered to players with {min_games}+ games: {filtered_count}/{initial_count}")
    
    # Standardize column names for rankings integration
    column_mapping = {
        'PLAYER NAME': 'PLAYER NAME',
        'Player': 'PLAYER NAME',
        'Pos': 'POS',
        'Team': 'TEAM'
    }
    
    df = df.rename(columns=column_mapping)
    
    # Select key columns for rankings integration
    rankings_columns = [
        'PLAYER_ID', 'PLAYER NAME', 'POS', 'TEAM',
        'TOTAL_FPTS', 'FPTS_PER_GAME',
        'RUSH_FPTS_PCT', 'REC_FPTS_PCT', 'PASS_FPTS_PCT', 'TD_FPTS_PCT',
        'FIRST_HALF_AVG', 'SECOND_HALF_AVG', 'AVG_NO_OUTLIERS',
        'CONSISTENCY_SCORE', 'COEFFICIENT_OF_VARIATION'
    ]
    
    # Only include columns that exist
    available_columns = [col for col in rankings_columns if col in df.columns]
    result_df = df[available_columns].copy()
    
    # Add prefix to distinguish historical stats in rankings
    history_columns = [col for col in result_df.columns 
                      if col not in ['PLAYER_ID', 'PLAYER NAME', 'POS', 'TEAM']]
    
    rename_dict = {col: f'HIST_{col}' for col in history_columns}
    result_df = result_df.rename(columns=rename_dict)
    
    if verbose:
        print(f"   ✓ Created rankings dataset: {len(result_df)} players, {len(result_df.columns)} columns")
        print(f"   ✓ Historical stats prefixed with 'HIST_' for integration")
    
    # Save to file if output directory specified
    if output_dir is not None:
        saved_path = save_historical_stats(result_df, output_dir, "rankings_ready_historical_stats", verbose)
        if verbose:
            print(f"\n💾 Rankings-ready dataset saved to: {saved_path}")
    
    return result_df


# Example usage and testing functions
def main():
    """Example usage of the player stats aggregation functions."""
    # Example paths - adjust as needed for your data
    season_data_path = "data/fpts historical/combined_data.csv"
    weekly_data_path = "data/fpts historical/weekly_data.csv"
    
    print("🏈 Player Stats Aggregation Example")
    print("=" * 50)
    
    try:
        # Aggregate historical stats (with file output)
        aggregated_stats = aggregate_player_historical_stats(
            season_data_path=season_data_path,
            weekly_data_path=weekly_data_path,
            season_filter=2024,  # Filter to 2024 season only
            output_dir="data/historical_stats/",  # Save aggregated data
            verbose=True
        )
        
        # Create rankings-ready dataset (with file output)
        rankings_ready = create_rankings_ready_dataset(
            aggregated_stats,
            current_season="2024",
            min_games=10,
            output_dir="data/rankings current/latest/",  # Save to rankings directory
            verbose=True
        )
        
        print(f"\n✅ Success! Aggregated {len(rankings_ready)} players for rankings integration")
        
        # Show sample of results
        print(f"\nSample of aggregated data:")
        sample_cols = ['PLAYER NAME', 'POS', 'HIST_TOTAL_FPTS', 'HIST_FIRST_HALF_AVG', 'HIST_SECOND_HALF_AVG']
        available_sample_cols = [col for col in sample_cols if col in rankings_ready.columns]
        print(rankings_ready[available_sample_cols].head())
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
