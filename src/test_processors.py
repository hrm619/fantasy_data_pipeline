"""
Test script for the modular data processors.

This script demonstrates how to use the individual data processors
and validates that they work correctly.
"""

import pandas as pd
import numpy as np
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

from fpts_processor import process_fpts_data, get_baseline_info
from fantasypros_processor import process_fantasypros_data, get_position_summary
from draftshark_adp_processor import process_draftshark_adp_data, get_adp_summary
from draftshark_rank_processor import process_draftshark_rank_data, validate_rankings
from utils import validate_dataframe, print_processing_summary


def create_sample_fpts_data():
    """Create sample FPTS data for testing."""
    data = {
        'PLAYER NAME': ['Player A', 'Player B', 'Player C', 'Player D', 'Player E'],
        'POS': ['QB', 'RB', 'WR', 'TE', 'QB'],
        'FPTS': [320.5, 280.3, 275.1, 180.7, 290.2]
    }
    return pd.DataFrame(data)


def create_sample_fantasypros_data():
    """Create sample FantasyPros data for testing."""
    data = {
        'PLAYER NAME': ['Player A', 'Player B', 'Player C', 'Player D'],
        'POS': ['QB1', 'RB1', 'WR1', 'TE1'],
        'RK': [1, 2, 3, 4]
    }
    return pd.DataFrame(data)


def create_sample_adp_data():
    """Create sample DraftShark ADP data for testing."""
    data = {
        'PLAYER NAME': ['Player A', 'Player B', 'Player C', 'Player D'],
        'POS': ['QB', 'RB', 'WR', 'TE'],
        'SLEEPER ADP': [1.2, 1.5, 2.1, 3.4]
    }
    return pd.DataFrame(data)


def create_sample_rank_data():
    """Create sample DraftShark ranking data for testing."""
    data = {
        'PLAYER NAME': ['Player A', 'Player B', 'Player C', 'Player D'],
        'POS': ['QB', 'RB', 'WR', 'TE']
    }
    return pd.DataFrame(data)


def test_fpts_processor():
    """Test the FPTS processor."""
    print("🧪 Testing FPTS Processor")
    print("=" * 40)
    
    # Create and process sample data
    df = create_sample_fpts_data()
    
    print("Original data:")
    print(df)
    
    # Process the data
    processed_df = process_fpts_data(df.copy(), verbose=True)
    
    print("\nProcessed data:")
    print(processed_df[['PLAYER NAME', 'POS', 'FPTS', 'VBD', 'RK', 'POS RANK']])
    
    # Get baseline info
    baseline_info = get_baseline_info(processed_df)
    print("\nBaseline info:")
    print(baseline_info)
    
    return processed_df


def test_fantasypros_processor():
    """Test the FantasyPros processor."""
    print("\n🧪 Testing FantasyPros Processor")
    print("=" * 40)
    
    # Create and process sample data
    df = create_sample_fantasypros_data()
    
    print("Original data:")
    print(df)
    
    # Process the data
    processed_df = process_fantasypros_data(df.copy(), verbose=True)
    
    print("\nProcessed data:")
    print(processed_df)
    
    # Get position summary
    summary = get_position_summary(processed_df)
    print("\nPosition summary:")
    print(summary)
    
    return processed_df


def test_adp_processor():
    """Test the DraftShark ADP processor."""
    print("\n🧪 Testing DraftShark ADP Processor")
    print("=" * 40)
    
    # Create and process sample data
    df = create_sample_adp_data()
    
    print("Original data:")
    print(df)
    
    # Process the data
    processed_df = process_draftshark_adp_data(df.copy(), verbose=True)
    
    print("\nProcessed data:")
    print(processed_df[['PLAYER NAME', 'SLEEPER ADP', 'ADP ROUND', 'ADP ROUND PICK', 'ADP RANK']])
    
    return processed_df


def test_rank_processor():
    """Test the DraftShark rank processor."""
    print("\n🧪 Testing DraftShark Rank Processor")
    print("=" * 40)
    
    # Create and process sample data
    df = create_sample_rank_data()
    
    print("Original data:")
    print(df)
    
    # Process the data
    processed_df = process_draftshark_rank_data(df.copy(), verbose=True)
    
    print("\nProcessed data:")
    print(processed_df)
    
    # Validate rankings
    validation = validate_rankings(processed_df)
    print("\nValidation results:")
    print(validation)
    
    return processed_df


def main():
    """Main function to run all tests."""
    print("🏈 Testing Fantasy Football Data Processors")
    print("=" * 60)
    
    try:
        # Test each processor
        fpts_result = test_fpts_processor()
        fp_result = test_fantasypros_processor()
        adp_result = test_adp_processor()
        rank_result = test_rank_processor()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("🎉 The modular processors are working correctly!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        raise


if __name__ == "__main__":
    main() 