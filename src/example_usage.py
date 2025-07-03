#!/usr/bin/env python3
"""
Example usage of the Fantasy Football Rankings Processor

This script demonstrates how to use the process_fantasy_rankings function
with different configuration options.
"""

from rankings_processor import process_fantasy_rankings
import os

def example_basic_usage():
    """
    Basic usage example with default parameters.
    """
    print("=== Basic Usage Example ===")
    
    try:
        # Process rankings with default settings
        output_file = process_fantasy_rankings(verbose=True)
        print(f"\n✅ Success! Rankings saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def example_custom_paths():
    """
    Example with custom file paths.
    """
    print("\n=== Custom Paths Example ===")
    
    try:
        # Process with custom paths
        output_file = process_fantasy_rankings(
            data_path="../data/rankings current/update/",
            player_key_path="../player_key_dict.json", 
            output_dir="./output/",
            verbose=True
        )
        print(f"\n✅ Success! Rankings saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def example_quiet_mode():
    """
    Example running in quiet mode (minimal output).
    """
    print("\n=== Quiet Mode Example ===")
    
    try:
        # Process with minimal output
        output_file = process_fantasy_rankings(verbose=False)
        print(f"✅ Rankings processed and saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Create output directory if it doesn't exist
    os.makedirs("./output", exist_ok=True)
    
    # Run examples
    example_basic_usage()
    # example_custom_paths()  # Uncomment to test custom paths
    # example_quiet_mode()    # Uncomment to test quiet mode 