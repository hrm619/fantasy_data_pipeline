"""
Fantasy Football Rankings Processor: Redraft

This module provides functionality to process fantasy football rankings data from multiple sources,
clean and standardize the data, calculate various ranking metrics, and output a consolidated CSV file.
"""

import pandas as pd
import os
import json
import sys
import shutil
from datetime import datetime

# Add scripts directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from scripts.load_data import load_data
from scripts.clean_cols_redraft import cols_dict

# Add src directory to path for processor imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from src.fpts_processor import process_fpts_data
from src.fp_processor import process_fantasypros_data
from src.ds_processor import process_draftshark_rank_data
from src.hw_processor import process_hw_data
from src.jj_processor import process_jj_data
from src.pff_processor import process_pff_data
from src.adp_processor import process_fantasypros_adp_data


def process_fantasy_rankings_redraft(
    data_path: str = "../data/rankings current/update/",
    player_key_path: str = "../player_key_dict.json",
    base_data_dir: str = "../data/rankings current/",
    verbose: bool = True
) -> str:
    """
    Process fantasy football rankings from multiple sources and create a consolidated ranking file.
    
    This function:
    1. Moves existing files from "latest" to "agg archive" if they exist
    2. Loads ranking files from the "update" directory
    3. Standardizes column names and adds player IDs
    4. Processes each ranking source with specific calculations
    5. Creates a consolidated ranking dataframe
    6. Saves the results to "latest" folder
    7. Moves processed files from "update" to "raw archive"
    
    Args:
        data_path (str): Path to directory containing ranking files (update folder)
        player_key_path (str): Path to player key dictionary JSON file
        base_data_dir (str): Base directory containing latest, update, agg archive, and raw archive folders
        verbose (bool): Whether to print detailed progress information
        
    Returns:
        str: Path to the generated CSV file
        
    Raises:
        ValueError: If required files are missing or data is invalid
        FileNotFoundError: If specified paths don't exist
    """
    
    if verbose:
        print("🏈 Starting Fantasy Football Rankings Processing")
        print("=" * 60)
    
    # Step 0: Set up directory paths
    latest_dir = os.path.join(base_data_dir, "latest")
    agg_archive_dir = os.path.join(base_data_dir, "agg archive")
    raw_archive_dir = os.path.join(base_data_dir, "raw archive")
    
    # Create directories if they don't exist
    os.makedirs(latest_dir, exist_ok=True)
    os.makedirs(agg_archive_dir, exist_ok=True)
    os.makedirs(raw_archive_dir, exist_ok=True)
    
    # Step 0.1: Move existing files from "latest" to "agg archive"
    if verbose:
        print("📁 Step 0.1: Checking for existing files in 'latest' folder...")
    
    if os.path.exists(latest_dir):
        existing_files = [f for f in os.listdir(latest_dir) if not f.startswith('.')]
        if existing_files:
            if verbose:
                print(f"   Found {len(existing_files)} files in 'latest' folder")
            
            # Create timestamped subfolder in agg archive
            timestamp = datetime.now().strftime("%Y%m%d_%H%M")
            archive_subfolder = os.path.join(agg_archive_dir, f"archived_{timestamp}")
            os.makedirs(archive_subfolder, exist_ok=True)
            
            for file in existing_files:
                src_path = os.path.join(latest_dir, file)
                dst_path = os.path.join(archive_subfolder, file)
                shutil.move(src_path, dst_path)
                if verbose:
                    print(f"   ✓ Moved {file} to agg archive")
        else:
            if verbose:
                print("   No files found in 'latest' folder")
    
    # Step 1: Load and validate input files
    if verbose:
        print("\n📁 Step 1: Loading ranking files from 'update' folder...")
    
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Data directory not found: {data_path}")
    
    # Get all files in the data directory
    files = [f for f in os.listdir(data_path) if not f.startswith('.')]
    files.sort()
    
    if len(files) < 1:
        raise ValueError(f"Expected at least 1 file, found {len(files)} in {data_path}")
    
    if verbose:
        print(f"   Found {len(files)} files to process")
        for i, file in enumerate(files[:6], 1):
            print(f"   {i}. {file}")
    
    # Step 2: Set up file mapping and load dataframes
    if verbose:
        print("\n📊 Step 2: Setting up file mapping and loading data...")
    
    # Create file mapping based on first 11 characters
    
    # TODO: move file_lookup to a config file
    file_lookup = { 
        "fpts":"Scott Barrett",
        "fp":"FantasyPros_2025_Draft_ALL_Rankings", 
        "jj":"Redraft1QB_",
        "ds":"rankings-half-ppr",
        "hw":"tableDownload",
        "pff":"Draft-rankings-export",
        "adp":"FantasyPros_2025_Overall_ADP_Rankings"}
    
    if verbose:
        print("   File mapping:")
        for key, gen_file in file_lookup.items():
            print(f"   {key}: {gen_file}")
    
    # Load each file into dataframes dictionary
    dataframes = {}
    for key, gen_file in file_lookup.items():
        matched_file = next((f for f in files if f.startswith(gen_file)), None)
        if matched_file:
            full_path = os.path.join(data_path, matched_file)
            dataframes[key] = load_data(full_path)
            if verbose:
                print(f"   ✓ Loaded {key}: {matched_file} ({len(dataframes[key])} rows)")
        else:
            raise ValueError(f"No file found for key '{key}' with prefix '{gen_file}'")
    
    # Step 3: Standardize column names and clean player names
    if verbose:
        print("\n🔧 Step 3: Standardizing column names and cleaning player names...")
    
    for key, df in dataframes.items():
        if key in cols_dict:
            original_cols = len(df.columns)
            df.columns = cols_dict[key]
            if verbose:
                print(f"   ✓ Updated {key}: {original_cols} columns standardized")
        
        # Clean player names by removing special characters and normalizing suffixes
        if 'PLAYER NAME' in df.columns:
            # First normalize common suffixes like "Jr." to "Jr"
            df['PLAYER NAME'] = df['PLAYER NAME'].str.replace(r'\bJr\.', 'Jr', regex=True)
            df['PLAYER NAME'] = df['PLAYER NAME'].str.replace(r'\bSr\.', 'Sr', regex=True)
            # Remove all other special characters except spaces
            df['PLAYER NAME'] = df['PLAYER NAME'].str.replace(r'[^\w\s]', '', regex=True)
            # Clean up extra whitespace
            df['PLAYER NAME'] = df['PLAYER NAME'].str.strip().str.replace(r'\s+', ' ', regex=True)
            if verbose:
                print(f"   ✓ Cleaned player names in {key}")
    
    # Step 4: Load player key dictionary and add player IDs
    if verbose:
        print("\n🔑 Step 4: Adding player IDs using player key dictionary...")
    
    if not os.path.exists(player_key_path):
        raise FileNotFoundError(f"Player key dictionary not found: {player_key_path}")
    
    with open(player_key_path, 'r') as f:
        player_key_dict = json.load(f)
    
    # Create reverse mapping from player names to keys
    player_name_to_key = {}
    for key, value in player_key_dict.items():
        if isinstance(value, list):
            for name in value:
                player_name_to_key[name] = key
        else:
            player_name_to_key[value] = key

    # Write player_name_to_key mapping to JSON file for debugging/reference
    if verbose:
        print("   Writing player name to key mapping to JSON file...")
    
    player_name_to_key_path = os.path.join('../data', 'player_name_to_key.json')
    with open(player_name_to_key_path, 'w') as f:
        json.dump(player_name_to_key, f, indent=4, sort_keys=True)
    
    if verbose:
        print(f"   ✓ Player name to key mapping saved to: {player_name_to_key_path}")
        print(f"   ✓ Total mappings created: {len(player_name_to_key)}")
    
    # Add PLAYER ID column to each dataframe
    for key, df in dataframes.items():
        df['PLAYER ID'] = df['PLAYER NAME'].map(player_name_to_key)
        total_players = len(df)
        matched_players = df['PLAYER ID'].notna().sum()
        match_rate = matched_players / total_players * 100
        if verbose:
            print(f"   {key}: {matched_players}/{total_players} players matched ({match_rate:.1f}%)")
    

    # Step 5: Process each data source with standardized output
    if verbose:
        print("\n📈 Step 5: Processing all data sources with standardized output...")
    
    # Process FPTS data with VBD calculations
    dataframes['fpts'] = process_fpts_data(dataframes['fpts'], verbose)
    
    # Process FantasyPros data
    dataframes['fp'] = process_fantasypros_data(dataframes['fp'], verbose)
    
    # Process DraftShark Rankings
    dataframes['ds'] = process_draftshark_rank_data(dataframes['ds'], verbose)
    
    # Process HW data
    dataframes['hw'] = process_hw_data(dataframes['hw'], verbose)
    
    # Process JJ data
    dataframes['jj'] = process_jj_data(dataframes['jj'], verbose)
    
    # Process PFF data
    dataframes['pff'] = process_pff_data(dataframes['pff'], verbose)
    
    # Process ADP data
    dataframes['adp'] = process_fantasypros_adp_data(dataframes['adp'], verbose)
    
    # Step 7: Create consolidated ranking dataframe
    if verbose:
        print("\n🔗 Step 7: Creating consolidated ranking dataframe...")
    
    # Start with player keys and get base info from fp (FantasyPros)
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
        # All processors now return standardized columns: RK, POS RANK, TIER, ADP
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
            
            # Only add prefixes for RK, POS RANK, and TIER columns
            rename_dict = {}
            for col in available_columns:
                # Only add prefixes to these specific columns
                if col in ['RK', 'POS RANK', 'TIER']:
                    if f'{col}_{key}' in df_rank.columns:
                        rename_dict[f'{col}_{key}'] = f'{key}_{col}'
                    elif col in df_rank.columns:
                        # This is the first occurrence, add prefix
                        rename_dict[col] = f'{key}_{col}'
                # All other columns (ADP, ADP ROUND, ECR, POS ECR) stay without prefix
            
            if rename_dict:
                df_rank = df_rank.rename(columns=rename_dict)
    
    # Step 8: Calculate Average Rankings
    if verbose:
        print("\n📊 Step 8: Calculating average rankings...")
    
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
    
    # 3. Calculate pos_ADP (positional rankings based on the ADP column)
    if 'ADP' in df_rank.columns and df_rank['ADP'].notna().any():
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
        df_rank['POS ADP'] = None
        if verbose:
            print("   ⚠ ADP column not found or has no data for pos_ADP calculation")



    # Step 9: Organize and clean final dataframe
    if verbose:
        print("\n📋 Step 9: Organizing and cleaning final dataframe...")
    
    # Reorder columns logically
    all_columns = list(df_rank.columns)
    base_columns = ['PLAYER ID', 'PLAYER NAME', 'POS', 'TEAM']
    
    # ADP ROUND column
    adp_round_columns = ['ADP ROUND'] if 'ADP ROUND' in all_columns else []
    
    # ADP column (should be clean without prefix)
    adp_columns = ['ADP'] if 'ADP' in all_columns else []

    # ECR column
    df_rank['ECR ADP Delta'] = df_rank['ADP'] - df_rank['ECR']
    ecr_columns = ['ECR', 'ECR ADP Delta']

    # Regular RK columns (excluding average)
    rk_columns = [col for col in all_columns if '_RK' in col and not col.startswith('avg_')]
    
    # RK columns
    df_rank['sd_RK'] = df_rank[rk_columns].std(axis=1, skipna=True)
    df_rank['ADP Delta'] = df_rank['ADP'] - df_rank['avg_RK']
    df_rank['ECR Delta'] = df_rank['ECR'] - df_rank['avg_RK']
    rk_calcs = ['avg_RK', 'sd_RK', 'ADP Delta', 'ECR Delta']

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
                           pos_rank_columns)
    other_columns = [col for col in all_columns if col not in categorized_columns]
    
    # Reorder columns according to specified order
    reordered_columns = categorized_columns + other_columns
    df_rank = df_rank[reordered_columns]
    
    # Filter to main positions and remove rows without essential data
    initial_rows = len(df_rank)
    df_rank = df_rank.dropna(subset=['ADP'])
    df_rank = df_rank[df_rank['POS'].isin(['WR', 'RB', 'QB', 'TE'])]
    final_rows = len(df_rank)
    # Sort by ADP in ascending order (best/earliest picks first)
    df_rank = df_rank.sort_values('ADP', ascending=True).reset_index(drop=True)
    
    if verbose:
        print(f"   ✓ Filtered from {initial_rows} to {final_rows} rows")
        print(f"   ✓ Kept players with main positions: QB, RB, WR, TE")
    
    # Step 9: Save results to "latest" folder
    if verbose:
        print("\n💾 Step 9: Saving results to 'latest' folder...")
    
    # Generate timestamped filename
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y%m%d_%H%M")
    filename = f'df_rank_clean_{timestamp}_redraft.csv'
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
    
    # Step 10: Move processed files from "update" to "raw archive"
    if verbose:
        print("\n📦 Step 10: Moving processed files to 'raw archive'...")
    
    # Create timestamped subfolder in raw archive
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
    
    if verbose:
        print("\n🎉 Rankings processing completed successfully!")
        print("=" * 60)
    
    return output_path


def main():
    """
    Main function to run the rankings processor with default parameters.
    Can be called directly from command line.
    """
    try:
        output_file = process_fantasy_rankings_redraft(
            data_path="../data/rankings current/update/",
            player_key_path="../player_key_dict.json",
            base_data_dir="../data/rankings current/",
            verbose=True
        )
        print(f"\nSuccess! Rankings saved to: {output_file}")
    except Exception as e:
        print(f"\nError processing rankings: {str(e)}")
        raise


if __name__ == "__main__":
    main() 