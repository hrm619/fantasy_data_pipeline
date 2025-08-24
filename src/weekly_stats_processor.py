"""
Weekly Stats Processor

Calculates trend statistics from weekly fantasy football data including
first half average, second half average, and average without outliers.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from .utils import validate_dataframe, safe_numeric_conversion, print_processing_summary


def calculate_weekly_trends(df: pd.DataFrame, 
                          outlier_method: str = 'percentile',
                          outlier_percentile: float = 10.0,
                          outlier_n_games: int = 2,
                          verbose: bool = True) -> pd.DataFrame:
    """
    Calculate weekly trend statistics from fantasy football weekly data.
    
    This function calculates:
    - First half average (weeks 1-9)
    - Second half average (weeks 10-18) 
    - Average without outliers (removing highest/lowest games)
    - Total games played
    - Best and worst game scores
    - Consistency metrics (standard deviation, coefficient of variation)
    
    Args:
        df (pd.DataFrame): DataFrame containing weekly stats with columns like:
                          Player, Pos, Team, and numbered week columns (1, 2, 3, etc.)
        outlier_method (str): Method for removing outliers ('percentile' or 'n_games')
                             'percentile': Remove games below/above certain percentiles
                             'n_games': Remove n highest and n lowest games
        outlier_percentile (float): Percentile threshold for outlier removal (10.0 = remove bottom/top 10%)
        outlier_n_games (int): Number of highest and lowest games to remove for outlier calculation
        verbose (bool): Whether to print progress information
        
    Returns:
        pd.DataFrame: Processed DataFrame with additional calculated fields:
                     - FIRST_HALF_AVG: Average fantasy points for weeks 1-9
                     - SECOND_HALF_AVG: Average fantasy points for weeks 10-18
                     - AVG_NO_OUTLIERS: Average fantasy points excluding outliers
                     - TOTAL_GAMES: Total number of games with valid scores
                     - BEST_GAME: Highest single-game fantasy points
                     - WORST_GAME: Lowest single-game fantasy points
                     - CONSISTENCY_SCORE: Standard deviation of weekly scores
                     - COEFFICIENT_OF_VARIATION: CV (std dev / mean) as consistency metric
    """
    if verbose:
        print("🔄 Processing weekly stats data...")
    
    # Make a copy to avoid modifying original
    df_processed = df.copy()
    
    # Validate basic required columns
    required_columns = ['PLAYER NAME', 'POS', 'TEAM']
    if not validate_dataframe(df_processed, required_columns):
        raise ValueError("Missing required columns for weekly stats processing")
    
    # Identify week columns (should be numbered 1-18)
    week_columns = _identify_week_columns(df_processed, verbose)
    
    if not week_columns:
        raise ValueError("No valid week columns found in the data")
    
    # Convert weekly data to numeric and handle missing values
    for col in week_columns:
        df_processed[col] = _clean_weekly_score(df_processed[col])
    
    # Calculate trend statistics
    _calculate_half_season_averages(df_processed, week_columns, verbose)
    _calculate_outlier_adjusted_average(df_processed, week_columns, outlier_method, 
                                       outlier_percentile, outlier_n_games, verbose)
    _calculate_consistency_metrics(df_processed, week_columns, verbose)
    _calculate_game_totals(df_processed, week_columns, verbose)
    
    # Select final columns
    output_columns = [
        'PLAYER NAME', 'POS', 'TEAM', '1H_PPG', '2H_PPG', 
        'NO_OUTLIERS_PPG', 'GAMES_PLAYED', 'BEST_GAME', 'WORST_GAME',
        'STD_DEV', 'CV'
    ]
    
    # Only include columns that exist
    available_columns = [col for col in output_columns if col in df_processed.columns]
    result_df = df_processed[available_columns].copy()
    
    if verbose:
        print_processing_summary(result_df, "Weekly Trends")
        _print_weekly_summary(result_df)
    
    return result_df


def _identify_week_columns(df: pd.DataFrame, verbose: bool) -> List[str]:
    """Identify columns that represent weekly scores (numbered 1-18)."""
    week_columns = []
    
    # Look for numeric column names that represent weeks (digits 1-18)
    for col in df.columns:
        # Check if column name is a number between 1 and 18
        if str(col).isdigit():
            week_num = int(col)
            if 1 <= week_num <= 18:
                week_columns.append(col)
    
    # Sort week columns numerically
    week_columns.sort(key=lambda x: int(str(x)) if str(x).isdigit() else 999)
    
    if verbose:
        print(f"   ✓ Found {len(week_columns)} week columns: {week_columns[:5]}{'...' if len(week_columns) > 5 else ''}")
    
    return week_columns


def _clean_weekly_score(series: pd.Series) -> pd.Series:
    """Clean weekly score data, handling various formats and missing values."""
    # Convert to string first to handle mixed types
    cleaned = series.astype(str)
    
    # Replace common indicators of missing games
    missing_indicators = ['BYE', 'bye', '-', '--', 'N/A', 'NA', 'null', 'None', '']
    for indicator in missing_indicators:
        cleaned = cleaned.replace(indicator, np.nan)
    
    # Convert to numeric, coercing errors to NaN
    return pd.to_numeric(cleaned, errors='coerce')


def _calculate_half_season_averages(df: pd.DataFrame, week_columns: List[str], verbose: bool) -> None:
    """Calculate first half (weeks 1-9) and second half (weeks 10-18) averages."""
    # Determine which weeks belong to first vs second half
    first_half_weeks = []
    second_half_weeks = []
    
    for col in week_columns:
        if str(col).isdigit():
            week_num = int(col)
            if week_num <= 9:
                first_half_weeks.append(col)
            else:
                second_half_weeks.append(col)
    
    # Calculate first half average
    if first_half_weeks:
        df['1H_PPG'] = df[first_half_weeks].mean(axis=1, skipna=True).round(2)
    else:
        df['1H_PPG'] = np.nan
    
    # Calculate second half average
    if second_half_weeks:
        df['2H_PPG'] = df[second_half_weeks].mean(axis=1, skipna=True).round(2)
    else:
        df['2H_PPG'] = np.nan
    
    if verbose:
        print(f"   ✓ Calculated half-season averages ({len(first_half_weeks)} + {len(second_half_weeks)} weeks)")


def _calculate_outlier_adjusted_average(df: pd.DataFrame, week_columns: List[str],
                                       method: str, percentile: float, n_games: int,
                                       verbose: bool) -> None:
    """Calculate average excluding the 2 highest and 2 lowest games (excluding zeros)."""
    outlier_averages = []
    
    for idx, row in df.iterrows():
        # Get all valid weekly scores for this player (excluding zeros)
        weekly_scores = []
        for col in week_columns:
            score = row[col]
            if pd.notna(score) and score > 0:  # Valid score, excluding zeros
                weekly_scores.append(float(score))
        
        # Need at least 5 games to remove 2 highest and 2 lowest
        if len(weekly_scores) < 5:
            outlier_averages.append(np.mean(weekly_scores) if weekly_scores else np.nan)
            continue
        
        # Sort scores and remove 2 highest and 2 lowest
        sorted_scores = sorted(weekly_scores)
        filtered_scores = sorted_scores[2:-2]  # Remove 2 lowest and 2 highest
        
        avg_no_outliers = np.mean(filtered_scores) if filtered_scores else np.nan
        outlier_averages.append(round(avg_no_outliers, 2) if pd.notna(avg_no_outliers) else np.nan)
    
    df['NO_OUTLIERS_PPG'] = outlier_averages
    
    if verbose:
        print(f"   ✓ Calculated averages excluding 2 highest and 2 lowest games (zeros excluded)")


def _calculate_consistency_metrics(df: pd.DataFrame, week_columns: List[str], verbose: bool) -> None:
    """Calculate consistency metrics including standard deviation and coefficient of variation."""
    std_scores = []
    cv_scores = []
    
    for idx, row in df.iterrows():
        # Get all valid weekly scores for this player
        weekly_scores = []
        for col in week_columns:
            score = row[col]
            if pd.notna(score) and score >= 0:
                weekly_scores.append(float(score))
        
        if len(weekly_scores) < 2:  # Need at least 2 games for std dev
            std_scores.append(np.nan)
            cv_scores.append(np.nan)
            continue
        
        # Calculate standard deviation
        std_dev = np.std(weekly_scores, ddof=1) if len(weekly_scores) > 1 else 0
        mean_score = np.mean(weekly_scores)
        
        # Calculate coefficient of variation (CV = std dev / mean)
        cv = (std_dev / mean_score * 100) if mean_score > 0 else np.nan
        
        std_scores.append(round(std_dev, 2))
        cv_scores.append(round(cv, 1) if pd.notna(cv) else np.nan)
    
    df['CONSISTENCY_SCORE'] = std_scores  # Lower is more consistent
    df['COEFFICIENT_OF_VARIATION'] = cv_scores  # Lower is more consistent
    
    if verbose:
        print("   ✓ Calculated consistency metrics (standard deviation and CV)")


def _calculate_game_totals(df: pd.DataFrame, week_columns: List[str], verbose: bool) -> None:
    """Calculate total games played and best/worst game scores."""
    games_played = []
    best_games = []
    worst_games = []
    
    for idx, row in df.iterrows():
        # Get all valid weekly scores for this player
        weekly_scores = []
        for col in week_columns:
            score = row[col]
            if pd.notna(score) and score >= 0:
                weekly_scores.append(float(score))
        
        games_played.append(len(weekly_scores))
        best_games.append(round(max(weekly_scores), 2) if weekly_scores else np.nan)
        worst_games.append(round(min(weekly_scores), 2) if weekly_scores else np.nan)
    
    df['TOTAL_GAMES'] = games_played
    df['BEST_GAME'] = best_games
    df['WORST_GAME'] = worst_games
    
    if verbose:
        print("   ✓ Calculated game totals and min/max scores")


def _print_weekly_summary(df: pd.DataFrame) -> None:
    """Print summary statistics for the weekly trends data."""
    print(f"\n📊 Weekly Trends Summary:")
    
    if 'TOTAL_GAMES' in df.columns:
        avg_games = df['TOTAL_GAMES'].mean()
        print(f"   Average games played: {avg_games:.1f}")
    
    if 'FIRST_HALF_AVG' in df.columns and 'SECOND_HALF_AVG' in df.columns:
        first_half_avg = df['FIRST_HALF_AVG'].mean()
        second_half_avg = df['SECOND_HALF_AVG'].mean()
        print(f"   League average - First half: {first_half_avg:.1f}, Second half: {second_half_avg:.1f}")
    
    if 'CONSISTENCY_SCORE' in df.columns:
        avg_consistency = df['CONSISTENCY_SCORE'].mean()
        print(f"   Average consistency score (std dev): {avg_consistency:.1f}")
    
    # Show breakdown by position if available
    if 'Pos' in df.columns:
        pos_stats = df.groupby('Pos').agg({
            'FIRST_HALF_AVG': 'mean',
            'SECOND_HALF_AVG': 'mean',
            'AVG_NO_OUTLIERS': 'mean',
            'CONSISTENCY_SCORE': 'mean'
        }).round(1)
        print(f"   Average stats by position:")
        for pos, stats in pos_stats.iterrows():
            print(f"     {pos}: 1H={stats['FIRST_HALF_AVG']:.1f}, 2H={stats['SECOND_HALF_AVG']:.1f}, "
                  f"No outliers={stats['AVG_NO_OUTLIERS']:.1f}, Consistency={stats['CONSISTENCY_SCORE']:.1f}")


def get_weekly_trends_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get summary statistics for weekly trends data by position.
    
    Args:
        df (pd.DataFrame): Processed weekly trends DataFrame
        
    Returns:
        pd.DataFrame: Summary statistics by position
    """
    if 'Pos' not in df.columns:
        return pd.DataFrame()
    
    summary_stats = df.groupby('Pos').agg({
        'FIRST_HALF_AVG': ['count', 'mean', 'median', 'std'],
        'SECOND_HALF_AVG': ['mean', 'median', 'std'],
        'AVG_NO_OUTLIERS': ['mean', 'median', 'std'],
        'CONSISTENCY_SCORE': ['mean', 'median'],
        'TOTAL_GAMES': 'mean'
    }).round(2)
    
    # Flatten column names
    summary_stats.columns = ['_'.join(col).strip() for col in summary_stats.columns.values]
    
    return summary_stats.reset_index()


def validate_weekly_trends(df: pd.DataFrame, verbose: bool = True) -> Dict[str, bool]:
    """
    Validate weekly trends calculations.
    
    Args:
        df (pd.DataFrame): Processed weekly trends DataFrame
        verbose (bool): Whether to print validation results
        
    Returns:
        Dict[str, bool]: Validation results for different checks
    """
    validation_results = {}
    
    # Check for reasonable game totals (should be between 1-18)
    validation_results['reasonable_game_totals'] = df['TOTAL_GAMES'].between(1, 18).all()
    
    # Check that best game >= worst game
    validation_results['best_gte_worst'] = (df['BEST_GAME'] >= df['WORST_GAME']).all()
    
    # Check for reasonable fantasy point averages (should be positive and < 60)
    avg_cols = ['FIRST_HALF_AVG', 'SECOND_HALF_AVG', 'AVG_NO_OUTLIERS']
    for col in avg_cols:
        if col in df.columns:
            reasonable_values = df[col].between(0, 60).all()
            validation_results[f'reasonable_{col.lower()}'] = reasonable_values
    
    # Check consistency scores are non-negative
    if 'CONSISTENCY_SCORE' in df.columns:
        validation_results['non_negative_consistency'] = (df['CONSISTENCY_SCORE'] >= 0).all()
    
    if verbose:
        print(f"\n✅ Weekly Trends Validation:")
        for check, passed in validation_results.items():
            status = "✓" if passed else "❌"
            print(f"   {status} {check.replace('_', ' ').title()}: {'Passed' if passed else 'Failed'}")
    
    return validation_results


def compare_half_season_performance(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Compare first half vs second half performance for trend analysis.
    
    Args:
        df (pd.DataFrame): Processed weekly trends DataFrame
        verbose (bool): Whether to print analysis results
        
    Returns:
        pd.DataFrame: DataFrame with performance comparison metrics
    """
    if not all(col in df.columns for col in ['FIRST_HALF_AVG', 'SECOND_HALF_AVG']):
        return pd.DataFrame()
    
    comparison_df = df[['Player', 'Pos', 'FIRST_HALF_AVG', 'SECOND_HALF_AVG']].copy()
    
    # Calculate difference and percentage change
    comparison_df['HALF_SEASON_DIFF'] = (comparison_df['SECOND_HALF_AVG'] - comparison_df['FIRST_HALF_AVG']).round(2)
    comparison_df['HALF_SEASON_PCT_CHANGE'] = (
        (comparison_df['HALF_SEASON_DIFF'] / comparison_df['FIRST_HALF_AVG'] * 100)
        .round(1)
    )
    
    # Categorize performance trends
    def categorize_trend(pct_change):
        if pd.isna(pct_change):
            return 'Insufficient Data'
        elif pct_change > 10:
            return 'Strong Improvement'
        elif pct_change > 5:
            return 'Moderate Improvement'
        elif pct_change > -5:
            return 'Consistent'
        elif pct_change > -10:
            return 'Moderate Decline'
        else:
            return 'Strong Decline'
    
    comparison_df['TREND_CATEGORY'] = comparison_df['HALF_SEASON_PCT_CHANGE'].apply(categorize_trend)
    
    if verbose:
        print(f"\n📈 Half-Season Performance Analysis:")
        trend_counts = comparison_df['TREND_CATEGORY'].value_counts()
        for trend, count in trend_counts.items():
            print(f"   {trend}: {count} players")
    
    return comparison_df
