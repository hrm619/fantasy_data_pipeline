"""
HW Rankings Scraper Module

Web scraper for Hayden Winks fantasy football rankings from Underdog Network.
Automatically extracts player rankings, statistics, and analysis.
"""

from .scraper import scrape_fantasy_rankings, match_player_name, load_player_key

__all__ = ['scrape_fantasy_rankings', 'match_player_name', 'load_player_key']
