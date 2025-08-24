#!/usr/bin/env python3
"""
Fantasy Football Rankings Processor - Main Entry Point

Simplified command-line interface for processing fantasy football rankings.
Replaces the original app/redraft_rankings_processor.py main function.
"""

import sys
import os
import argparse

# Add parent directory to path to import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src import RankingsProcessor


def main():
    """Main function with command-line argument support."""
    parser = argparse.ArgumentParser(description='Process fantasy football rankings')
    parser.add_argument('--league-type', choices=['redraft', 'bestball'], default='redraft',
                       help='Type of league to process (default: redraft)')
    parser.add_argument('--data-path', help='Path to update directory containing ranking files')
    parser.add_argument('--player-key-path', help='Path to player key dictionary JSON file')
    parser.add_argument('--base-data-dir', help='Base directory containing latest, update, archive folders')
    parser.add_argument('--quiet', action='store_true', help='Suppress verbose output')
    
    args = parser.parse_args()
    
    try:
        processor = RankingsProcessor(args.league_type)
        
        output_file = processor.process_rankings(
            data_path=args.data_path,
            player_key_path=args.player_key_path,
            base_data_dir=args.base_data_dir,
            verbose=not args.quiet
        )
        
        print(f"\n✅ Success! Rankings saved to: {output_file}")
        return 0
        
    except Exception as e:
        print(f"\n❌ Error processing rankings: {str(e)}")
        if not args.quiet:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
