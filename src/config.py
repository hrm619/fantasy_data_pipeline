"""
Configuration module for fantasy football data processing.

Centralizes all column mappings, file lookups, and constants.
"""

# Standard column names for different data sources
COLUMN_MAPPINGS = {
    # FPTS data (Scott Barrett)
    'fpts': [
        'RK',
        'PLAYER NAME',
        'POS',
        'TEAM',
        'BYE',
        'TIER',
        'EXODIA'
    ],
    
    # FantasyPros data
    'fp': [
        'ECR', 
        'TIER', 
        'PLAYER NAME', 
        'TEAM', 
        'POS', 
        'BYE',
        'SOS',
        'ECR VS ADP'
    ],
    
    # JJ Zachariason data
    'jj': [
        'RK',
        'PLAYER NAME', 
        'POS',
        'POS RANK',
        'TIER',
        'AUCTION'
    ],
    
    # DraftShark rankings
    'ds': [
        'RK',
        'TEAM',
        'PLAYER NAME',
        'POS',
        'G',
        'DS ADP',
        'BYE',
        'SOS',
        'INJURY RISK',
        'FLOOR PROJ',
        'CONS PROJ',
        'DS PROJ',
        'CEILING PROJ',
        '3D VALUE'
    ],
    
    # Hayden Winks data
    'hw': [
        'PLAYER NAME',
        'RK',
        'UNDERDOG ADP',
        'DIFF',
        'FINISH-2024',
        'TEAM',
        'POS',
        'POS RANK',
        'NOTES',
        'ID'
    ],
    
    # PFF data
    'pff': [
        'RK',
        'PLAYER NAME',
        'TEAM',
        'POS',
        'POS RANK',
        'BYE',
        'PFF ADP',
        'PROJ',
        'AUCTION'
    ],
    
    # ADP data
    'adp': [
        'PLAYER NAME',
        'TEAM',
        'BYE',
        'POS',
        'ADP',
        'MARKET INDEX',
        'RT'
    ]
}

# File lookup patterns for different league types
FILE_MAPPINGS = {
    'redraft': {
        "fpts": "Scott Barrett",
        "fp": "FantasyPros_2025_Draft_ALL_Rankings", 
        "jj": "Redraft1QB_",
        "ds": "rankings-half-ppr",
        "hw": "tableDownload",
        "pff": "Draft-rankings-export",
        "adp": "FantasyPros_2025_Overall_ADP_Rankings"
    },
    'bestball': {
        "fpts": "Scott Barrett",
        "fp": "FantasyPros_2025_Draft_ALL_Rankings", 
        "jj": "1QBRankings_",
        "ds": "rankings-half-ppr",
        "hw": "tableDownload",
        "pff": "Draft-rankings-export",
        "adp": "adp-rankings"
    }
}

# Supported fantasy positions
SUPPORTED_POSITIONS = ['QB', 'RB', 'WR', 'TE']

# Default paths
DEFAULT_PATHS = {
    'data_dir': 'data/rankings current/',
    'update_dir': 'data/rankings current/update/',
    'latest_dir': 'data/rankings current/latest/',
    'agg_archive_dir': 'data/rankings current/agg archive/',
    'raw_archive_dir': 'data/rankings current/raw archive/',
    'player_key_file': 'player_key_dict.json'
}

# Standardized output columns for all processors
STANDARD_OUTPUT_COLUMNS = {
    'base': ['PLAYER NAME', 'PLAYER ID', 'POS', 'TEAM'],
    'ranking': ['RK', 'POS RANK'],
    'optional': ['TIER', 'ADP', 'ECR', 'POS ECR', 'ADP ROUND']
}
