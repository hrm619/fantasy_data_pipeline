"""
Player name utilities for fantasy football data processing.

Functions for cleaning player names and managing player key mappings.
"""

import pandas as pd
import json
import os
from typing import Dict, Any


def clean_player_names(df: pd.DataFrame, player_name_col: str = 'PLAYER NAME') -> pd.DataFrame:
    """
    Clean player names by removing special characters and normalizing suffixes.
    
    Args:
        df (pd.DataFrame): DataFrame containing player names
        player_name_col (str): Name of the column containing player names
        
    Returns:
        pd.DataFrame: DataFrame with cleaned player names
    """
    if player_name_col not in df.columns:
        return df
        
    df_clean = df.copy()
    
    # Normalize common suffixes like "Jr." to "Jr"
    df_clean[player_name_col] = df_clean[player_name_col].str.replace(r'\bJr\.', 'Jr', regex=True)
    df_clean[player_name_col] = df_clean[player_name_col].str.replace(r'\bSr\.', 'Sr', regex=True)
    
    # Remove all other special characters except spaces
    df_clean[player_name_col] = df_clean[player_name_col].str.replace(r'[^\w\s]', '', regex=True)
    
    # Clean up extra whitespace
    df_clean[player_name_col] = df_clean[player_name_col].str.strip().str.replace(r'\s+', ' ', regex=True)
    
    return df_clean


def load_player_key_mapping(player_key_path: str, save_reverse_mapping: bool = True) -> tuple[Dict[str, Any], Dict[str, str]]:
    """
    Load player key dictionary and create reverse mapping.
    
    Args:
        player_key_path (str): Path to player key dictionary JSON file
        save_reverse_mapping (bool): Whether to save the reverse mapping to a file
        
    Returns:
        tuple: (player_key_dict, player_name_to_key_dict)
        
    Raises:
        FileNotFoundError: If player key file doesn't exist
    """
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
    
    # Optionally save reverse mapping for debugging/reference
    if save_reverse_mapping:
        reverse_mapping_path = os.path.join('data', 'player_name_to_key.json')
        os.makedirs(os.path.dirname(reverse_mapping_path), exist_ok=True)
        with open(reverse_mapping_path, 'w') as f:
            json.dump(player_name_to_key, f, indent=4, sort_keys=True)
    
    return player_key_dict, player_name_to_key


def add_player_ids(df: pd.DataFrame, player_name_to_key: Dict[str, str], 
                   player_name_col: str = 'PLAYER NAME', verbose: bool = True) -> pd.DataFrame:
    """
    Add PLAYER ID column to dataframe using player name mapping.
    
    Args:
        df (pd.DataFrame): DataFrame to add player IDs to
        player_name_to_key (Dict[str, str]): Mapping from player names to IDs
        player_name_col (str): Name of the column containing player names
        verbose (bool): Whether to print match statistics
        
    Returns:
        pd.DataFrame: DataFrame with PLAYER ID column added
    """
    df_with_ids = df.copy()
    df_with_ids['PLAYER ID'] = df_with_ids[player_name_col].map(player_name_to_key)
    
    if verbose:
        total_players = len(df_with_ids)
        matched_players = df_with_ids['PLAYER ID'].notna().sum()
        match_rate = matched_players / total_players * 100 if total_players > 0 else 0
        print(f"   Player ID matching: {matched_players}/{total_players} players matched ({match_rate:.1f}%)")
    
    return df_with_ids
