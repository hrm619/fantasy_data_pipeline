"""
Unified Fantasy Football Rankings Processor

Simplified and consolidated version that replaces rankings_processor.py, 
redraft_rankings_processor.py, and bb_rankings_processor.py with a single
flexible processor that handles all league types.

Based on redraft_rankings_processor.py as the source of truth.
"""

import pandas as pd
import os
import json
import shutil
from datetime import datetime
from typing import Dict, List, Optional

from .config import (
    COLUMN_MAPPINGS, WEEKLY_COLUMN_MAPPINGS, ROS_COLUMN_MAPPINGS,
    FILE_MAPPINGS, SUPPORTED_POSITIONS, DEFAULT_PATHS, get_weekly_file_mappings
)
from .data_loader import load_data
from .player_utils import clean_player_names, load_player_key_mapping, add_player_ids
from .base_processor import (
    process_fpts_data, process_fantasypros_data, process_draftshark_rank_data,
    process_hw_data, process_jj_data, process_pff_data, process_fantasypros_adp_data
)
from .hw_scraper_integration import auto_scrape_if_needed


class RankingsProcessor:
    """
    Unified processor for fantasy football rankings from multiple sources.

    Handles all league types (redraft, bestball, weekly, ros) with a single implementation.
    """

    def __init__(self, league_type: str = 'redraft', week: int = None):
        """
        Initialize the rankings processor.

        Args:
            league_type (str): Type of league ('redraft', 'bestball', 'weekly', or 'ros')
            week (int): Week number for weekly rankings (required when league_type is 'weekly')
        """
        if league_type not in FILE_MAPPINGS:
            raise ValueError(f"Unsupported league type: {league_type}. Supported types: {list(FILE_MAPPINGS.keys())}")

        if league_type == 'weekly' and week is None:
            raise ValueError("Week number is required for weekly league type")

        self.league_type = league_type
        self.week = week
        self.is_ros = league_type == 'ros'

        # Set file mapping based on league type
        if league_type == 'weekly':
            self.file_mapping = get_weekly_file_mappings(week)
        else:
            self.file_mapping = FILE_MAPPINGS[league_type]

        # Processor mapping - exclude ADP for weekly/ROS
        self.processors = {
            'fpts': process_fpts_data,
            'fp': process_fantasypros_data,
            'ds': process_draftshark_rank_data,
            'hw': process_hw_data,
            'jj': process_jj_data,
            'pff': process_pff_data,
        }

        # Only add ADP processor for redraft/bestball league types
        if league_type not in ['weekly', 'ros']:
            self.processors['adp'] = process_fantasypros_adp_data
    
    def process_rankings(self,
                        data_path: str = None,
                        player_key_path: str = None,
                        base_data_dir: str = None,
                        week: int = None,
                        verbose: bool = True) -> str:
        """
        Process fantasy football rankings from multiple sources and create a consolidated ranking file.
        
        Args:
            data_path (str): Path to directory containing ranking files (update folder)
            player_key_path (str): Path to player key dictionary JSON file
            base_data_dir (str): Base directory containing latest, update, agg archive, and raw archive folders
            week (int): Week number for weekly rankings (overrides week from constructor)
            verbose (bool): Whether to print detailed progress information
            
        Returns:
            str: Path to the generated CSV file
        """
        # Handle week parameter for weekly rankings
        if self.league_type == 'weekly':
            if week is not None:
                # Update week if provided in method call
                self.week = week
                self.file_mapping = get_weekly_file_mappings(week)
            elif self.week is None:
                raise ValueError("Week number is required for weekly rankings")
        # Use defaults if not provided
        data_path = data_path or DEFAULT_PATHS['update_dir']
        player_key_path = player_key_path or DEFAULT_PATHS['player_key_file']
        base_data_dir = base_data_dir or DEFAULT_PATHS['data_dir']
        
        if verbose:
            print("🏈 Starting Fantasy Football Rankings Processing")
            if self.league_type == 'weekly':
                print(f"   League Type: {self.league_type.upper()} - Week {self.week}")
            else:
                print(f"   League Type: {self.league_type.upper()}")
            print("=" * 60)
        
        # Step 0: Setup directories
        dirs = self._setup_directories(base_data_dir, verbose)
        
        # Step 0.1: Archive existing files
        self._archive_existing_files(dirs['latest'], dirs['agg_archive'], verbose)

        # Step 0.2: Auto-scrape HW rankings for weekly/ROS if needed
        if self.league_type in ['weekly', 'ros']:
            try:
                auto_scrape_if_needed(
                    week=self.week,
                    league_type=self.league_type,
                    data_path=data_path,
                    force=False,
                    verbose=verbose
                )
            except Exception as e:
                if verbose:
                    print(f"   ⚠️  HW scraping failed: {e}")
                    print(f"   Continuing with existing files (if any)...")

        # Step 1: Load input files
        files = self._load_input_files(data_path, verbose)
        
        # Step 2: Load and standardize data
        dataframes = self._load_and_standardize_data(data_path, files, verbose)
        
        # Step 3: Add player IDs
        player_key_dict, dataframes = self._add_player_ids(dataframes, player_key_path, verbose)
        
        # Step 4: Process all data sources
        dataframes = self._process_data_sources(dataframes, verbose)
        
        # Step 5: Create consolidated rankings
        df_rank = self._create_consolidated_rankings(dataframes, player_key_dict, verbose)
        
        # Step 6: Calculate average rankings
        df_rank = self._calculate_average_rankings(df_rank, verbose)

        # Step 7: Merge weekly/ROS data if applicable
        df_rank = self._merge_weekly_ros_data(df_rank, dataframes, verbose)

        # Step 8: Merge historical stats if available (redraft/bestball only)
        df_rank = self._merge_historical_stats(df_rank, dirs['latest'], verbose)
        
        # Step 8: Organize and clean final dataframe
        df_rank = self._organize_final_dataframe(df_rank, verbose)
        
        # Step 9: Save results
        output_path = self._save_results(df_rank, dirs['latest'], verbose)
        
        # Step 10: Archive processed files
        self._archive_processed_files(data_path, files, dirs['raw_archive'], verbose)
        
        if verbose:
            print("\n🎉 Rankings processing completed successfully!")
            print("=" * 60)
        
        return output_path
    
    def _setup_directories(self, base_data_dir: str, verbose: bool) -> Dict[str, str]:
        """Setup and create necessary directories."""
        dirs = {
            'latest': os.path.join(base_data_dir, "latest"),
            'agg_archive': os.path.join(base_data_dir, "agg archive"),
            'raw_archive': os.path.join(base_data_dir, "raw archive")
        }
        
        for dir_path in dirs.values():
            os.makedirs(dir_path, exist_ok=True)
            
        return dirs
    
    def _archive_existing_files(self, latest_dir: str, agg_archive_dir: str, verbose: bool):
        """Move existing files from latest to agg archive."""
        if verbose:
            print("📁 Step 0.1: Checking for existing files in 'latest' folder...")
        
        if not os.path.exists(latest_dir):
            return
            
        existing_files = [f for f in os.listdir(latest_dir) if not f.startswith('.')]
        # Keep historical stats files in place for merging
        files_to_archive = [f for f in existing_files if not f.startswith('rankings_ready_historical_stats_')]
        
        if files_to_archive:
            if verbose:
                print(f"   Found {len(existing_files)} files in 'latest' folder")
                if len(existing_files) > len(files_to_archive):
                    historical_files = [f for f in existing_files if f.startswith('rankings_ready_historical_stats_')]
                    print(f"   Keeping {len(historical_files)} historical stats files for merging")
            
            # Create timestamped subfolder in agg archive
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            archive_subfolder = os.path.join(agg_archive_dir, f"archived_{timestamp}")
            os.makedirs(archive_subfolder, exist_ok=True)
            
            for file in files_to_archive:
                src_path = os.path.join(latest_dir, file)
                dst_path = os.path.join(archive_subfolder, file)
                shutil.move(src_path, dst_path)
                if verbose:
                    print(f"   ✓ Moved {file} to agg archive")
        else:
            if verbose:
                print("   No files found in 'latest' folder")
    
    def _load_input_files(self, data_path: str, verbose: bool) -> List[str]:
        """Load and validate input files."""
        if verbose:
            print("\n📁 Step 1: Loading ranking files from 'update' folder...")
        
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"Data directory not found: {data_path}")
        
        files = [f for f in os.listdir(data_path) if not f.startswith('.')]
        files.sort()
        
        if len(files) < 1:
            raise ValueError(f"Expected at least 1 file, found {len(files)} in {data_path}")
        
        if verbose:
            print(f"   Found {len(files)} files to process")
            for i, file in enumerate(files[:6], 1):
                print(f"   {i}. {file}")
        
        return files
    
    def _load_and_standardize_data(self, data_path: str, files: List[str], verbose: bool) -> Dict[str, pd.DataFrame]:
        """Load data files and standardize column names."""
        if verbose:
            print("\n📊 Step 2: Setting up file mapping and loading data...")
        
        if verbose:
            print("   File mapping:")
            for key, gen_file in self.file_mapping.items():
                print(f"   {key}: {gen_file}")
        
        # Load each file into dataframes dictionary
        dataframes = {}
        for key, gen_file in self.file_mapping.items():
            # Handle special case where gen_file is a list (for multiple files like FPTS position files)
            if isinstance(gen_file, list):
                combined_dfs = []
                for prefix in gen_file:
                    matched_files = [f for f in files if f.startswith(prefix)]
                    if not matched_files:
                        raise ValueError(f"No files found for key '{key}' with prefix '{prefix}'")
                    
                    # Load all files that match this prefix
                    for matched_file in matched_files:
                        full_path = os.path.join(data_path, matched_file)

                        # Handle special case for PFF weekly/ROS files (header in second row)
                        if self.league_type in ['weekly', 'ros'] and key == 'pff':
                            df = load_data(full_path, header_row=1)  # Use second row as header for PFF weekly/ROS
                        else:
                            df = load_data(full_path)

                        combined_dfs.append(df)
                        if verbose:
                            print(f"   ✓ Loaded {key} file: {matched_file} ({len(df)} rows)")
                
                # Concatenate all DataFrames for this key
                if combined_dfs:
                    dataframes[key] = pd.concat(combined_dfs, ignore_index=True)
                    if verbose:
                        print(f"   ✓ Combined {len(combined_dfs)} files for {key}: total {len(dataframes[key])} rows")
                else:
                    raise ValueError(f"No data loaded for key '{key}'")
            else:
                # Handle single file case (existing logic)
                matched_file = next((f for f in files if f.startswith(gen_file)), None)
                if matched_file:
                    full_path = os.path.join(data_path, matched_file)

                    # Handle special cases for file loading
                    if self.league_type == 'weekly' and key in ['fp', 'pff']:
                        # FP and PFF weekly files have header in second row
                        dataframes[key] = load_data(full_path, header_row=1)
                    elif self.league_type == 'ros' and key == 'pff':
                        # PFF ROS files have header in second row
                        dataframes[key] = load_data(full_path, header_row=1)
                    elif self.league_type == 'ros' and key == 'jj':
                        # JJ ROS file needs second sheet "Rankings and Tiers"
                        dataframes[key] = load_data(full_path, sheet_name="Rankings and Tiers")
                    else:
                        dataframes[key] = load_data(full_path)

                    if verbose:
                        print(f"   ✓ Loaded {key}: {matched_file} ({len(dataframes[key])} rows)")
                else:
                    raise ValueError(f"No file found for key '{key}' with prefix '{gen_file}'")
        
        # Standardize column names and clean player names
        if verbose:
            print("\n🔧 Step 3: Standardizing column names and cleaning player names...")
        
        for key, df in dataframes.items():
            # Choose column mappings based on league type
            if self.league_type == 'weekly':
                column_mappings = WEEKLY_COLUMN_MAPPINGS
            elif self.league_type == 'ros':
                column_mappings = ROS_COLUMN_MAPPINGS
            else:
                column_mappings = COLUMN_MAPPINGS

            if key in column_mappings:
                expected_cols = column_mappings[key]
                if len(df.columns) == len(expected_cols):
                    df.columns = expected_cols
                    if verbose:
                        print(f"   ✓ Updated {key}: {len(df.columns)} columns standardized")
                else:
                    if verbose:
                        print(f"   ⚠️  Column count mismatch for {key}: expected {len(expected_cols)}, got {len(df.columns)}")
                        print(f"        Expected: {expected_cols}")
                        print(f"        Actual columns: {list(df.columns)}")
                    continue
            
            # Clean player names
            dataframes[key] = clean_player_names(df)
            if verbose and 'PLAYER NAME' in df.columns:
                print(f"   ✓ Cleaned player names in {key}")

        return dataframes
    
    def _add_player_ids(self, dataframes: Dict[str, pd.DataFrame], player_key_path: str, verbose: bool) -> tuple:
        """Add player IDs using player key dictionary."""
        if verbose:
            print("\n🔑 Step 4: Adding player IDs using player key dictionary...")

        player_key_dict, player_name_to_key = load_player_key_mapping(player_key_path)

        if verbose:
            print(f"   ✓ Player name to key mapping saved to: data/player_name_to_key.json")
            print(f"   ✓ Total mappings created: {len(player_name_to_key)}")

        # Add PLAYER ID column to each dataframe
        for key, df in dataframes.items():
            # Skip adding player IDs if already present (e.g., from HW scraper output)
            if 'PLAYER ID' in df.columns:
                if verbose:
                    print(f"   ℹ️  {key}: PLAYER ID already present, skipping ID assignment")
                continue

            dataframes[key] = add_player_ids(df, player_name_to_key, verbose=verbose)

        return player_key_dict, dataframes
    
    def _process_data_sources(self, dataframes: Dict[str, pd.DataFrame], verbose: bool) -> Dict[str, pd.DataFrame]:
        """Process each data source with standardized output."""
        if verbose:
            print("\n📈 Step 5: Processing all data sources with standardized output...")

        for key, df in dataframes.items():
            # Skip processing hw-data and fpts-data - these are for merging only
            if key in ['hw-data', 'fpts-data']:
                if verbose:
                    print(f"   ℹ️  Skipping processing for {key} (will be merged later)")
                continue

            if key in self.processors:
                # Pass league_type to each processor
                dataframes[key] = self.processors[key](df, verbose, self.league_type)
            else:
                if verbose:
                    print(f"   ⚠️  No processor found for {key}, skipping...")

        return dataframes
    
    def _create_consolidated_rankings(self, dataframes: Dict[str, pd.DataFrame],
                                    player_key_dict: Dict, verbose: bool) -> pd.DataFrame:
        """Create consolidated ranking dataframe."""
        if verbose:
            print("\n🔗 Step 7: Creating consolidated ranking dataframe...")

        # Start with player keys and get base info from fp source
        df_rank = pd.DataFrame({'PLAYER ID': list(player_key_dict.keys())})

        df_rank = df_rank.merge(
            dataframes['fp'][['PLAYER ID', 'PLAYER NAME', 'POS', 'TEAM']],
            on='PLAYER ID',
            how='left'
        )

        # Clean player names
        df_rank['PLAYER NAME'] = df_rank['PLAYER NAME'].str.replace(r'[^\w\s]', '', regex=True)
        
        # Merge ranking data from all sources with standardized columns
        for key, df in dataframes.items():
            # Skip hw-data and fpts-data - these are merged separately later
            if key in ['hw-data', 'fpts-data']:
                continue

            # Define columns to join based on league type
            if self.league_type in ['weekly', 'ros']:
                # For weekly/ROS: only POS RANK, TIER, ECR, POS ECR (no RK or ADP)
                columns_to_join = ['POS RANK', 'TIER', 'ECR', 'POS ECR']
            else:
                # For redraft/bestball: all standard columns including RK and ADP
                columns_to_join = ['RK', 'POS RANK', 'TIER', 'ADP', 'ECR', 'POS ECR']

                # For ADP source, also include ADP ROUND
                if key == 'adp':
                    columns_to_join.append('ADP ROUND')

            # Only join columns that exist and have data
            available_columns = [col for col in columns_to_join if col in df.columns]
            
            if available_columns:
                join_columns = ['PLAYER ID'] + available_columns
                df_rank = df_rank.merge(
                    df[join_columns],
                    on='PLAYER ID',
                    how='left',
                    suffixes=('', f'_{key}')
                )
                
                # Add prefixes for ranking and tier columns
                rename_dict = {}
                for col in available_columns:
                    # Add prefixes to ranking and tier columns
                    prefix_columns = ['RK', 'POS RANK', 'TIER'] if self.league_type not in ['weekly', 'ros'] else ['POS RANK', 'TIER']
                    if col in prefix_columns:
                        if f'{col}_{key}' in df_rank.columns:
                            rename_dict[f'{col}_{key}'] = f'{key}_{col}'
                        elif col in df_rank.columns:
                            # This is the first occurrence, add prefix
                            rename_dict[col] = f'{key}_{col}'
                    # All other columns (ADP, ADP ROUND, ECR, POS ECR) stay without prefix
                
                if rename_dict:
                    df_rank = df_rank.rename(columns=rename_dict)

        return df_rank
    
    def _calculate_average_rankings(self, df_rank: pd.DataFrame, verbose: bool) -> pd.DataFrame:
        """Calculate average rankings."""
        if verbose:
            print("\n📊 Step 8: Calculating average rankings...")
        
        # For weekly/ROS rankings, skip overall RK calculations and focus on POS RANK only
        if self.league_type not in ['weekly', 'ros']:
            # 1. Calculate avg_RK (average of columns with '_RK' in title, excluding POS RANK columns)
            rk_columns_for_avg = [col for col in df_rank.columns if '_RK' in col and 'POS' not in col]
            if rk_columns_for_avg:
                df_rank['avg_RK'] = df_rank[rk_columns_for_avg].mean(axis=1, skipna=True)
                if verbose:
                    print(f"   ✓ Calculated avg_RK from {len(rk_columns_for_avg)} ranking columns: {rk_columns_for_avg}")
            else:
                df_rank['avg_RK'] = None
                if verbose:
                    print("   ⚠ No _RK columns found for avg_RK calculation")
        else:
            if verbose:
                print(f"   ℹ️ Skipping avg_RK calculation for {self.league_type} rankings")
        
        # 2. Calculate avg_POS RANK (average of columns with '_POS RANK' in title)
        pos_rank_columns_for_avg = [col for col in df_rank.columns if '_POS RANK' in col]
        if pos_rank_columns_for_avg:
            df_rank['avg_POS RANK'] = df_rank[pos_rank_columns_for_avg].mean(axis=1, skipna=True)
            if verbose:
                print(f"   ✓ Calculated avg_POS RANK from {len(pos_rank_columns_for_avg)} position ranking columns: {pos_rank_columns_for_avg}")
        else:
            df_rank['avg_POS RANK'] = None
            if verbose:
                print("   ⚠ No _POS RANK columns found for avg_POS RANK calculation")
        
        # 3. Calculate pos_ADP (positional rankings based on the ADP column) - skip for weekly/ROS
        if self.league_type not in ['weekly', 'ros'] and 'ADP' in df_rank.columns and df_rank['ADP'].notna().any():
            df_rank['POS ADP'] = df_rank.groupby('POS')['ADP'].rank(method='min', na_option='keep').astype('Int64')
            if verbose:
                print("   ✓ Calculated pos_ADP (positional rankings based on ADP)")
                # Show breakdown by position
                for pos in df_rank['POS'].unique():
                    if pd.notna(pos):
                        pos_data = df_rank[df_rank['POS'] == pos]['POS ADP'].dropna()
                        if len(pos_data) > 0:
                            print(f"     {pos}: {len(pos_data)} players ranked 1-{int(pos_data.max())}")
        else:
            if self.league_type in ['weekly', 'ros']:
                if verbose:
                    print(f"   ℹ️ Skipping pos_ADP calculation for {self.league_type} rankings")
            else:
                df_rank['POS ADP'] = None
                if verbose:
                    print("   ⚠ ADP column not found or has no data for pos_ADP calculation")
        
        return df_rank

    def _merge_weekly_ros_data(self, df_rank: pd.DataFrame, dataframes: Dict[str, pd.DataFrame], verbose: bool) -> pd.DataFrame:
        """Merge weekly/ROS data files (hw-data and fpts-data) for weekly and ROS league types."""
        # Only merge for weekly/ROS league types
        if self.league_type not in ['weekly', 'ros']:
            return df_rank

        if verbose:
            print(f"\n📊 Step 7.5: Merging weekly/ROS data...")

        # Step 1: Merge hw-data (HPPR, Exp, Diff) first
        if 'hw-data' in dataframes:
            hw_data = dataframes['hw-data'].copy()

            # Keep only the fields we need: PLAYER ID, HPPR, EXP, DIFF
            hw_columns_to_keep = ['PLAYER ID', 'HPPR', 'EXP', 'DIFF']
            hw_data_clean = hw_data[[col for col in hw_columns_to_keep if col in hw_data.columns]]

            # Merge with rankings
            initial_cols = len(df_rank.columns)
            df_rank = df_rank.merge(hw_data_clean, on='PLAYER ID', how='left')

            if verbose:
                hw_data_count = df_rank['HPPR'].notna().sum() if 'HPPR' in df_rank.columns else 0
                print(f"   ✓ Merged HW data (HPPR, EXP, DIFF)")
                print(f"   ✓ {hw_data_count}/{len(df_rank)} players have HW data")

        # Step 2: Merge fpts-data (numeric fields only, excluding already present columns)
        if 'fpts-data' in dataframes:
            fpts_data = dataframes['fpts-data'].copy()

            # Get all numeric columns except those already in the output
            numeric_cols = fpts_data.select_dtypes(include=['number']).columns.tolist()

            # Exclude columns that are already in df_rank or shouldn't be included
            excluded_cols = ['RK', 'POS RANK', 'BYE'] + list(df_rank.columns)
            fpts_columns_to_keep = ['PLAYER ID'] + [col for col in numeric_cols
                                                      if col not in excluded_cols and col != 'PLAYER ID']

            fpts_data_clean = fpts_data[[col for col in fpts_columns_to_keep if col in fpts_data.columns]]

            # Merge with rankings
            df_rank = df_rank.merge(fpts_data_clean, on='PLAYER ID', how='left')

            if verbose:
                added_cols = len(df_rank.columns) - initial_cols - 3  # Subtract the 3 HW columns
                if 'FPTS' in df_rank.columns:
                    fpts_data_count = df_rank['FPTS'].notna().sum()
                    print(f"   ✓ Merged FPTS data ({added_cols} numeric fields)")
                    print(f"   ✓ {fpts_data_count}/{len(df_rank)} players have FPTS data")

        return df_rank

    def _merge_historical_stats(self, df_rank: pd.DataFrame, latest_dir: str, verbose: bool) -> pd.DataFrame:
        """Merge historical stats (for redraft/bestball) or weekly/ROS data (for weekly/ROS)."""
        if verbose:
            print("\n📊 Step 8.5: Checking for historical stats to merge...")

        # For weekly/ROS, skip historical stats entirely
        if self.league_type in ['weekly', 'ros']:
            if verbose:
                print(f"   ℹ️  Skipping historical stats for {self.league_type} league type")
            return df_rank

        # For redraft/bestball, merge historical stats
        # Look for the latest historical stats file
        historical_stats_files = [f for f in os.listdir(latest_dir)
                                if f.startswith('rankings_ready_historical_stats_') and f.endswith('.csv')]

        if historical_stats_files:
            # Get the most recent historical stats file
            latest_hist_file = sorted(historical_stats_files)[-1]
            hist_file_path = os.path.join(latest_dir, latest_hist_file)

            try:
                # Load historical stats
                hist_df = pd.read_csv(hist_file_path)

                # Select only historical stats columns (avoid duplicates)
                hist_columns_to_merge = ['PLAYER ID'] + [col for col in hist_df.columns if col.startswith('HIST_')]
                hist_df_clean = hist_df[hist_columns_to_merge]

                # Merge with rankings
                initial_cols = len(df_rank.columns)
                df_rank = df_rank.merge(hist_df_clean, on='PLAYER ID', how='left')

                # Calculate merge statistics
                hist_data_count = df_rank[df_rank.columns[df_rank.columns.str.startswith('HIST_')]].notna().any(axis=1).sum()
                hist_data_rate = (hist_data_count / len(df_rank) * 100) if len(df_rank) > 0 else 0

                if verbose:
                    print(f"   ✓ Found and merged historical stats from: {hist_file_path}")
                    print(f"   ✓ Added {len(df_rank.columns) - initial_cols} historical stat columns")
                    print(f"   ✓ {hist_data_count}/{len(df_rank)} players have historical data ({hist_data_rate:.1f}%)")

            except Exception as e:
                if verbose:
                    print(f"   ⚠️  Could not load historical stats from {hist_file_path}: {e}")
        else:
            if verbose:
                print("   ℹ️  No historical stats files found (run player_stats.py first)")

        return df_rank
    
    def _organize_final_dataframe(self, df_rank: pd.DataFrame, verbose: bool) -> pd.DataFrame:
        """Organize and clean final dataframe."""
        if verbose:
            print("\n📋 Step 9: Organizing and cleaning final dataframe...")
        
        # Remove any duplicate columns that may have been created during merges
        df_rank = df_rank.loc[:, ~df_rank.columns.duplicated()].copy()
        
        # Reorder columns logically
        all_columns = list(df_rank.columns)
        base_columns = ['PLAYER ID', 'PLAYER NAME', 'POS', 'TEAM']

        # HW data columns (HPPR, EXP, DIFF) - for weekly/ROS league types
        hw_data_columns = []
        if self.league_type in ['weekly', 'ros']:
            hw_data_columns = [col for col in ['HPPR', 'EXP', 'DIFF'] if col in all_columns]

        # FPTS data columns (numeric fields from fpts-xfp-avg) - for weekly/ROS league types
        fpts_data_columns = []
        if self.league_type in ['weekly', 'ros']:
            # Get all columns that came from fpts-data merge (not in base, hw-data, or ranking columns)
            reserved_columns = base_columns + hw_data_columns + ['avg_POS RANK']
            reserved_patterns = ['_POS RANK', '_TIER', '_RK', 'ECR', 'ADP', 'PLAYER ID']
            fpts_data_columns = [col for col in all_columns
                                if col not in reserved_columns
                                and not any(pattern in col for pattern in reserved_patterns)]

        # ADP ROUND column
        adp_round_columns = ['ADP ROUND'] if 'ADP ROUND' in all_columns else []
        
        # ADP column (should be clean without prefix)
        adp_columns = ['ADP'] if 'ADP' in all_columns else []

        # ECR column - check if both ECR and ADP exist before calculating delta
        ecr_columns = []
        if 'ECR' in df_rank.columns:
            ecr_columns.append('ECR')
            if 'ADP' in df_rank.columns:
                df_rank['ECR ADP Delta'] = df_rank['ADP'] - df_rank['ECR']
                ecr_columns.append('ECR ADP Delta')

        # Regular RK columns (excluding average)
        rk_columns = [col for col in all_columns if '_RK' in col and not col.startswith('avg_')]
        
        # RK columns and calculations - skip for weekly/ROS
        rk_calcs = []
        if self.league_type not in ['weekly', 'ros']:
            df_rank['sd_RK'] = df_rank[rk_columns].std(axis=1, skipna=True)
            if 'ADP' in df_rank.columns:
                df_rank['ADP Delta'] = df_rank['ADP'] - df_rank['avg_RK']
            if 'ECR' in df_rank.columns:
                df_rank['ECR Delta'] = df_rank['ECR'] - df_rank['avg_RK']
            rk_calcs = ['avg_RK', 'sd_RK']
            if 'ADP' in df_rank.columns:
                rk_calcs.append('ADP Delta')
            if 'ECR' in df_rank.columns:
                rk_calcs.append('ECR Delta')

        # Tier columns
        tier_columns = [col for col in all_columns if '_TIER' in col] 
        
        # POS ECR column
        pos_ecr_columns = ['POS ECR'] if 'POS ECR' in all_columns else []

        # Regular positional rank columns (excluding average)
        pos_rank_columns = [col for col in all_columns if '_POS RANK' in col and not col.startswith('avg_')]
        
        # Average positional rank columns
        avg_pos_rank_columns = [col for col in all_columns if col.startswith('avg_') and 'POS' in col]
        
        # positional ADP column
        pos_adp_columns = ['POS ADP'] if 'POS ADP' in all_columns else []

        # Any remaining columns not categorized above
        categorized_columns = (base_columns +
                               adp_round_columns +
                               adp_columns +
                               ecr_columns +
                               rk_calcs +
                               rk_columns +
                               tier_columns +
                               pos_adp_columns +
                               pos_ecr_columns +
                               avg_pos_rank_columns +
                               pos_rank_columns +
                               hw_data_columns +
                               fpts_data_columns)
        other_columns = [col for col in all_columns if col not in categorized_columns]
        
        # Reorder columns according to specified order
        reordered_columns = categorized_columns + other_columns
        df_rank = df_rank[reordered_columns]
        
        # Filter to main positions and remove rows without essential data
        initial_rows = len(df_rank)

        # For weekly/ROS rankings, filter by avg_POS RANK instead of ADP
        if self.league_type in ['weekly', 'ros']:
            df_rank = df_rank.dropna(subset=['avg_POS RANK'])
            df_rank = df_rank[df_rank['POS'].isin(SUPPORTED_POSITIONS)]
            # Sort by avg_POS RANK in ascending order (best positional ranks first)
            df_rank = df_rank.sort_values('avg_POS RANK', ascending=True).reset_index(drop=True)
        else:
            df_rank = df_rank.dropna(subset=['ADP'])
            df_rank = df_rank[df_rank['POS'].isin(SUPPORTED_POSITIONS)]
            # Sort by ADP in ascending order (best/earliest picks first)
            df_rank = df_rank.sort_values('ADP', ascending=True).reset_index(drop=True)
            
        final_rows = len(df_rank)
        
        if verbose:
            print(f"   ✓ Filtered from {initial_rows} to {final_rows} rows")
            print(f"   ✓ Kept players with main positions: {', '.join(SUPPORTED_POSITIONS)}")
        
        return df_rank
    
    def _save_results(self, df_rank: pd.DataFrame, latest_dir: str, verbose: bool) -> str:
        """Save results to latest folder."""
        if verbose:
            print("\n💾 Step 9: Saving results to 'latest' folder...")
        
        # Generate timestamped filename
        current_time = datetime.now()
        timestamp = current_time.strftime("%Y%m%d_%H%M")
        
        # Include week number in filename for weekly rankings
        if self.league_type == 'weekly':
            filename = f'df_rank_clean_{timestamp}_{self.league_type}_week{self.week}.csv'
        else:
            filename = f'df_rank_clean_{timestamp}_{self.league_type}.csv'
            
        output_path = os.path.join(latest_dir, filename)
        
        # Save to CSV
        df_rank.to_csv(output_path, index=False)
        
        if verbose:
            print(f"   ✓ Data saved to: {output_path}")
            print(f"   ✓ Final dataset contains {len(df_rank)} players")
            print(f"   ✓ Columns: {len(df_rank.columns)} total")
            
            # Show position breakdown
            pos_counts = df_rank['POS'].value_counts()
            print("   Position breakdown:")
            for pos, count in pos_counts.items():
                print(f"     {pos}: {count} players")
        
        return output_path
    
    def _archive_processed_files(self, data_path: str, files: List[str], 
                               raw_archive_dir: str, verbose: bool):
        """Move processed files from update to raw archive."""
        if verbose:
            print("\n📦 Step 10: Moving processed files to 'raw archive'...")
        
        # Create timestamped subfolder in raw archive
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        raw_archive_subfolder = os.path.join(raw_archive_dir, f"processed_{timestamp}")
        os.makedirs(raw_archive_subfolder, exist_ok=True)
        
        files_moved = 0
        for file in files:
            src_path = os.path.join(data_path, file)
            dst_path = os.path.join(raw_archive_subfolder, file)
            if os.path.exists(src_path):
                shutil.move(src_path, dst_path)
                files_moved += 1
                if verbose:
                    print(f"   ✓ Moved {file} to raw archive")
        
        if verbose:
            print(f"   ✓ Total files moved to raw archive: {files_moved}")


# Convenience functions for different league types
def process_redraft_rankings(**kwargs) -> str:
    """Process redraft league rankings."""
    processor = RankingsProcessor('redraft')
    return processor.process_rankings(**kwargs)

def process_bestball_rankings(**kwargs) -> str:
    """Process bestball league rankings."""
    processor = RankingsProcessor('bestball')
    return processor.process_rankings(**kwargs)

def process_weekly_rankings(week: int = None, **kwargs) -> str:
    """Process weekly league rankings."""
    processor = RankingsProcessor('weekly', week)
    return processor.process_rankings(**kwargs)

def process_ros_rankings(**kwargs) -> str:
    """Process rest-of-season (ROS) league rankings."""
    processor = RankingsProcessor('ros')
    return processor.process_rankings(**kwargs)

def process_fantasy_rankings_redraft(**kwargs) -> str:
    """Backward compatibility function for redraft rankings."""
    return process_redraft_rankings(**kwargs)
