"""
Base processor class that eliminates code duplication across all ranking processors.

This consolidates the common logic found in fpts_processor, fp_processor, hw_processor, 
jj_processor, pff_processor, ds_processor, and adp_processor.
"""

import pandas as pd
from typing import List, Dict, Any, Optional
from ..config import STANDARD_OUTPUT_COLUMNS, WEEKLY_OUTPUT_COLUMNS, ROS_OUTPUT_COLUMNS


class BaseProcessor:
    """
    Base class for processing ranking data from different sources.
    
    All processors follow the same pattern:
    1. Create/validate ranking columns
    2. Calculate positional rankings 
    3. Return standardized output columns
    """
    
    def __init__(self, source_name: str, league_type: str = 'redraft'):
        """
        Initialize processor for a specific data source.

        Args:
            source_name (str): Name of the data source (e.g., 'fpts', 'fp', 'jj')
            league_type (str): Type of league ('redraft', 'bestball', 'weekly', 'ros')
        """
        self.source_name = source_name
        self.league_type = league_type
        self.is_weekly = league_type == 'weekly'
        self.is_ros = league_type == 'ros'
        
    def process(self, df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
        """
        Process ranking data and return standardized columns.

        Args:
            df (pd.DataFrame): Raw ranking data
            verbose (bool): Whether to print progress information

        Returns:
            pd.DataFrame: Processed data with standardized columns
        """
        if verbose:
            print(f"🔄 Processing {self.source_name} ranking data...")

        df_processed = df.copy()

        # Step 0: Clean position data BEFORE calculating rankings (must happen first!)
        df_processed = self._clean_position_data(df_processed, verbose)

        # Step 1: Handle ranking columns
        df_processed = self._ensure_ranking_columns(df_processed, verbose)

        # Step 2: Calculate positional rankings
        df_processed = self._calculate_positional_rankings(df_processed, verbose)

        # Step 3: Handle special cases for specific processors
        df_processed = self._handle_special_cases(df_processed, verbose)

        # Step 4: Return standardized columns
        result_df = self._standardize_output(df_processed, verbose)

        if verbose:
            self._print_summary(result_df)

        return result_df
    
    def _clean_position_data(self, df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
        """
        Clean position data by removing numbers (e.g., "QB1" -> "QB").
        Must run BEFORE calculating positional rankings.
        """
        if 'POS' not in df.columns:
            return df

        # For FantasyPros and ADP sources, clean position data
        if self.source_name in ['fp', 'adp']:
            original_values = df['POS'].unique()
            df['POS'] = df['POS'].str.replace(r'\d+', '', regex=True)
            if verbose and any(pd.notna(original_values)):
                # Only show message if positions actually had numbers
                if any(val for val in original_values if pd.notna(val) and any(c.isdigit() for c in str(val))):
                    print(f"   ✓ Cleaned position data (removed position numbers)")

        return df

    def _ensure_ranking_columns(self, df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
        """Ensure required ranking columns exist."""
        # For weekly and ROS rankings, we skip overall RK creation and focus on positional rankings
        if not self.is_weekly and not self.is_ros:
            # Create overall ranking if not present
            if 'RK' not in df.columns and 'ECR' not in df.columns:
                df['RK'] = df.index + 1
                if verbose:
                    print("   ✓ Created RK column using index values")

        # Ensure ranking columns are integer type
        for col in ['RK', 'ECR']:
            if col in df.columns:
                df[col] = df[col].astype('Int64')

        return df
    
    def _calculate_positional_rankings(self, df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
        """Calculate positional rankings based on overall rank."""
        if 'POS' not in df.columns:
            return df

        # Use ECR for FantasyPros data, RK for others
        rank_col = 'ECR' if 'ECR' in df.columns and self.source_name == 'fp' else 'RK'
        pos_rank_col = 'POS ECR' if rank_col == 'ECR' else 'POS RANK'

        # Only calculate positional rankings if:
        # 1. The rank column exists, AND
        # 2. The positional rank column doesn't already exist (e.g., from HW scraper)
        if rank_col in df.columns and pos_rank_col not in df.columns:
            df[pos_rank_col] = df.groupby('POS')[rank_col].rank(method='min').astype('Int64')

        return df
    
    def _handle_special_cases(self, df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
        """Handle processor-specific logic."""
        # Note: Position cleaning now happens in _clean_position_data() BEFORE calculating rankings

        # ADP processor: Calculate ADP ROUND from ADP
        if self.source_name == 'adp' and 'ADP' in df.columns:
            df['ADP ROUND'] = ((df['ADP'] - 1) // 12 + 1).astype('Int64')

        # HW processor: Use HPPR RANK as POS RANK for weekly and ROS rankings
        if self.source_name == 'hw' and (self.is_weekly or self.is_ros):
            if 'HPPR RANK' in df.columns and 'POS RANK' not in df.columns:
                df['POS RANK'] = df['HPPR RANK'].astype('Int64')
                if verbose:
                    print("   ✓ Created POS RANK from HPPR RANK for HW data")

        return df
    
    def _standardize_output(self, df: pd.DataFrame, verbose: bool) -> pd.DataFrame:
        """Return standardized output columns."""
        # Choose column structure based on league type
        if self.is_weekly:
            column_config = WEEKLY_OUTPUT_COLUMNS
        elif self.is_ros:
            column_config = ROS_OUTPUT_COLUMNS
        else:
            column_config = STANDARD_OUTPUT_COLUMNS
        
        # Base required columns
        base_columns = column_config['base'].copy()
        
        # Add ranking columns that exist
        ranking_columns = []
        for col in column_config['ranking']:
            if col in df.columns:
                ranking_columns.append(col)
        
        # Add ECR columns for FantasyPros (if not weekly or if weekly allows ECR)
        if self.source_name == 'fp':
            for col in ['ECR', 'POS ECR']:
                if col in df.columns and col in column_config['optional']:
                    ranking_columns.append(col)
        
        # Add optional columns that exist
        optional_columns = []
        for col in column_config['optional']:
            if col in df.columns:
                optional_columns.append(col)
        
        # Build final column list
        final_columns = base_columns + ranking_columns + optional_columns
        
        # Ensure all required columns exist (fill with NA if missing)
        for col in final_columns:
            if col not in df.columns:
                df[col] = pd.NA
                if verbose and col not in ['TEAM']:  # Don't warn for TEAM since it's expected to be missing from HW scraper
                    print(f"   ⚠ Added missing column: {col}")
        
        return df[final_columns].copy()
    
    def _print_summary(self, df: pd.DataFrame):
        """Print processing summary."""
        print(f"   ✓ {self.source_name.upper()} rankings processed")
        print(f"   Total players: {len(df)}")
        
        # Show position breakdown if available
        if 'POS' in df.columns:
            pos_counts = df['POS'].value_counts()
            print("   Position breakdown:")
            for pos, count in pos_counts.items():
                print(f"     {pos}: {count} players")
        
        print(f"   ✓ Returned {len(df)} players with standardized columns")


# Convenience functions for each processor type
def process_fpts_data(df: pd.DataFrame, verbose: bool = True, league_type: str = 'redraft') -> pd.DataFrame:
    """Process FPTS ranking data."""
    processor = BaseProcessor('fpts', league_type)
    return processor.process(df, verbose)

def process_fantasypros_data(df: pd.DataFrame, verbose: bool = True, league_type: str = 'redraft') -> pd.DataFrame:
    """Process FantasyPros ranking data.""" 
    processor = BaseProcessor('fp', league_type)
    return processor.process(df, verbose)

def process_hw_data(df: pd.DataFrame, verbose: bool = True, league_type: str = 'redraft') -> pd.DataFrame:
    """Process Hayden Winks ranking data."""
    processor = BaseProcessor('hw', league_type)
    return processor.process(df, verbose)

def process_jj_data(df: pd.DataFrame, verbose: bool = True, league_type: str = 'redraft') -> pd.DataFrame:
    """Process JJ Zachariason ranking data."""
    processor = BaseProcessor('jj', league_type)
    return processor.process(df, verbose)

def process_pff_data(df: pd.DataFrame, verbose: bool = True, league_type: str = 'redraft') -> pd.DataFrame:
    """Process PFF ranking data."""
    processor = BaseProcessor('pff', league_type)
    return processor.process(df, verbose)

def process_draftshark_rank_data(df: pd.DataFrame, verbose: bool = True, league_type: str = 'redraft') -> pd.DataFrame:
    """Process DraftShark ranking data."""
    processor = BaseProcessor('ds', league_type)
    return processor.process(df, verbose)

def process_fantasypros_adp_data(df: pd.DataFrame, verbose: bool = True, league_type: str = 'redraft') -> pd.DataFrame:
    """Process FantasyPros ADP data."""
    processor = BaseProcessor('adp', league_type)
    return processor.process(df, verbose)
