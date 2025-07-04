"""
Fantasy Football Rankings Processor

This module provides functionality to process fantasy football rankings data from multiple sources,
clean and standardize the data, calculate various ranking metrics, and output a consolidated CSV file.
"""

import pandas as pd
import numpy as np
import os
import json
import sys
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add scripts directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath('')))
from scripts.load_data import load_data
from scripts.clean_cols import cols_dict

# Add src directory to path for processor imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from src.fpts_processor import process_fpts_data
from src.fantasypros_processor import process_fantasypros_data
from src.draftshark_adp_processor import process_draftshark_adp_data
from src.draftshark_rank_processor import process_draftshark_rank_data


def process_fantasy_rankings(
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
    
    lookup_keys = [
        "fpts",
        "fantasypros", 
        "jj",
        "draftshark_adp",
        "draftshark_rank",
        "hayden_winks"
    ]
    
    # Create file mapping based on first 11 characters
    generalized_files = [f[:11] for f in files[:len(lookup_keys)]]
    file_lookup = dict(zip(lookup_keys, generalized_files))
    
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
    
    # Step 5: Process FPTS data with VBD calculations
    if verbose:
        print("\n📈 Step 5: Processing FPTS data with VBD calculations...")
    
    dataframes['fpts'] = process_fpts_data(dataframes['fpts'], verbose)
    
    # Step 6: Process other ranking sources
    if verbose:
        print("\n🔄 Step 6: Processing other ranking sources...")
    
    # Process FantasyPros data
    dataframes['fantasypros'] = process_fantasypros_data(dataframes['fantasypros'], verbose)
    
    # Process DraftShark ADP data
    dataframes['draftshark_adp'] = process_draftshark_adp_data(dataframes['draftshark_adp'], verbose)
    
    # Process DraftShark Rankings
    dataframes['draftshark_rank'] = process_draftshark_rank_data(dataframes['draftshark_rank'], verbose)
    
    # Step 7: Create consolidated ranking dataframe
    if verbose:
        print("\n🔗 Step 7: Creating consolidated ranking dataframe...")
    
    # Start with player keys and get base info from fantasypros
    df_rank = pd.DataFrame({'PLAYER ID': list(player_key_dict.keys())})
    df_rank = df_rank.merge(
        dataframes['fantasypros'][['PLAYER ID', 'PLAYER NAME', 'POS']], 
        on='PLAYER ID', 
        how='left'
    )
    
    # Clean player names
    df_rank['PLAYER NAME'] = df_rank['PLAYER NAME'].str.replace(r'[^\w\s]', '', regex=True)
    
    # Add ADP data
    df_rank = df_rank.merge(
        dataframes['draftshark_adp'][['PLAYER ID', 'ADP ROUND', 'ADP ROUND PICK', 'ADP RANK']],
        on='PLAYER ID',
        how='left'
    )
    
    # Merge ranking data from all sources
    for key, df in dataframes.items():
        columns_to_join = []
        
        # Check for relevant columns
        if 'RK' in df.columns:
            columns_to_join.append('RK')
        if 'POS RANK' in df.columns:
            columns_to_join.append('POS RANK')
        if 'TIER' in df.columns:
            columns_to_join.append('TIER')
        
        if columns_to_join:
            join_columns = ['PLAYER ID'] + columns_to_join
            df_rank = df_rank.merge(
                df[join_columns],
                on='PLAYER ID',
                how='left',
                suffixes=('', f'_{key}')
            )
            
            # Rename columns with prefix
            rename_dict = {col: f'{key}_{col}' for col in columns_to_join}
            df_rank = df_rank.rename(columns=rename_dict)
    
    # Step 8: Organize and clean final dataframe
    if verbose:
        print("\n📋 Step 8: Organizing and cleaning final dataframe...")
    
    # Reorder columns logically
    all_columns = list(df_rank.columns)
    adp_columns = [col for col in all_columns if 'ADP' in col]
    rk_columns = [col for col in all_columns if 'RK' in col and 'POS' not in col]
    pos_rank_columns = [col for col in all_columns if 'POS RANK' in col]
    tier_columns = [col for col in all_columns if 'TIER' in col]
    other_columns = [col for col in all_columns if col not in rk_columns + pos_rank_columns + tier_columns + adp_columns]
    
    reordered_columns = other_columns + adp_columns + rk_columns + pos_rank_columns + tier_columns
    df_rank = df_rank[reordered_columns]
    
    # Filter to main positions and remove rows without essential data
    initial_rows = len(df_rank)
    df_rank = df_rank.dropna(subset=['PLAYER NAME', 'ADP ROUND'])
    df_rank = df_rank[df_rank['POS'].isin(['WR', 'RB', 'QB', 'TE'])]
    final_rows = len(df_rank)
    
    if verbose:
        print(f"   ✓ Filtered from {initial_rows} to {final_rows} rows")
        print(f"   ✓ Kept players with main positions: QB, RB, WR, TE")
    
    # Step 9: Save results to "latest" folder
    if verbose:
        print("\n💾 Step 9: Saving results to 'latest' folder...")
    
    # Generate timestamped filename
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y%m%d_%H%M")
    filename = f'df_rank_clean_{timestamp}.csv'
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
        output_file = process_fantasy_rankings(
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