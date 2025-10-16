"""
Fantasy Football Rankings Scraper for Underdog Network

Scrapes Hayden Winks fantasy football rankings from Underdog Network articles,
extracting player rankings, statistics, and analysis by position.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import json
import os
from difflib import SequenceMatcher


def load_player_key():
    """
    Load the player key dictionary from player_key_dict.json

    Returns:
        dict: Player key dictionary mapping player IDs to name variations
    """
    # Get the path relative to this file - go up to project root
    # Current: src/fantasy_pipeline/scraper/hw_scraper.py
    # Need to go up 3 levels: scraper/ -> fantasy_pipeline/ -> src/ -> project_root/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    key_path = os.path.join(project_root, 'player_key_dict.json')

    with open(key_path, 'r') as f:
        return json.load(f)


def match_player_name(scraped_name, player_key):
    """
    Match a scraped player name to the player key dictionary.

    Uses case-insensitive exact matching first, then fuzzy matching with a threshold.

    Args:
        scraped_name (str): Player name as scraped from the website
        player_key (dict): Player key dictionary with ID -> name list mappings

    Returns:
        tuple: (player_id, standardized_name) or (None, None) if no match
    """
    scraped_lower = scraped_name.lower().strip()

    # Try exact match first (case-insensitive)
    for player_id, name_list in player_key.items():
        for name in name_list:
            if name.lower().strip() == scraped_lower:
                return (player_id, name_list[0])  # Return ID and first name in list

    # Try fuzzy matching with high threshold (0.85)
    best_match = None
    best_score = 0.85  # Minimum threshold

    for player_id, name_list in player_key.items():
        for name in name_list:
            # Calculate similarity ratio
            ratio = SequenceMatcher(None, scraped_lower, name.lower().strip()).ratio()
            if ratio > best_score:
                best_score = ratio
                best_match = (player_id, name_list[0])

    return best_match if best_match else (None, None)


def scrape_fantasy_rankings(url):
    """
    Scrape fantasy football rankings from Underdog Network

    Extracts player rankings by position (QB, RB, WR, TE) including:
    - Player names with standardized IDs
    - Position ranks
    - Yardage statistics
    - Analysis details

    Args:
        url (str): URL of the Underdog Network rankings page

    Returns:
        pd.DataFrame: DataFrame with columns:
            - Player Name: Name as it appears on the website
            - Player ID: Standardized player identifier
            - Standardized Name: Canonical player name from player key
            - Position: Player position (QB, RB, WR, TE)
            - Position Rank: Rank within position
            - Yards Stat: Projected yards/completions/receptions
            - Details: Analysis text for the player
    """
    # Fetch the webpage
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    # Parse HTML
    soup = BeautifulSoup(response.content, 'html.parser')

    # Get the main content text - Next.js renders everything in one continuous line
    content = soup.get_text()

    # Load player key dictionary
    player_key = load_player_key()

    players_data = []

    # Split content by position headers
    position_sections = {
        'QB': re.search(r'Week \d+ QB Rankings(.*?)(?=Week \d+ (?:RB|WR|TE) Rankings|$)', content, re.DOTALL),
        'RB': re.search(r'Week \d+ RB Rankings(.*?)(?=Week \d+ (?:WR|TE|QB) Rankings|$)', content, re.DOTALL),
        'WR': re.search(r'Week \d+ WR Rankings(.*?)(?=Week \d+ (?:TE|QB) Rankings|$)', content, re.DOTALL),
        'TE': re.search(r'Week \d+ TE Rankings(.*?)(?=Week \d+ QB Rankings|$)', content, re.DOTALL),
    }

    for position, section_match in position_sections.items():
        if not section_match:
            continue

        section_text = section_match.group(1)

        # Match player entries: "PlayerName - XX.X yards/completions/receptions in Underdog's Pick'em"
        # The pattern captures the player name before " - " and yardage stats
        # Updated to handle McCaffrey, St. Brown, Smith-Njigba, D'Andre, etc.
        player_pattern = r"([A-Z][A-Za-z\.''-]+(?:\s+[A-Z][A-Za-z\.''-]+)*)\s+-\s+([\d.]+)\s+(?:total yards|receiving yards|completions|receptions)\s+in\s+Underdog['\u2019]s Pick['\u2019]em"

        matches = []
        for match in re.finditer(player_pattern, section_text):
            player_name = match.group(1)
            yards_stat = match.group(2)

            # Clean up player names by removing common contaminating prefixes
            # These are team names, acronyms, or other words that appear before actual player names
            contaminating_prefixes = [
                'NFL. ', 'NFL.', 'Giants. ', 'Giants.', 'Lions. ', 'Lions.',
                'Panthers. ', 'Panthers.', 'WRs. ', 'WRs.', 'Saints. ', 'Saints.',
                'Bengals. ', 'Bengals.', 'Tonges. ', 'Tonges.'
            ]

            for prefix in contaminating_prefixes:
                if player_name.startswith(prefix):
                    player_name = player_name[len(prefix):]
                    break

            # Handle concatenated names: if any word has multiple capitals and isn't Mc/Mac, split and take last part
            words = player_name.split()
            cleaned_words = []
            for word in words:
                # Count capitals - if more than expected for Mc/Mac names, it's likely concatenated
                capitals = [i for i, c in enumerate(word) if c.isupper()]
                if len(capitals) >= 2 and not word.startswith(('Mc', 'Mac', 'St.', 'De')):
                    # Find last capital and split there
                    last_cap_idx = capitals[-1]
                    # Look for pattern: lowercase then uppercase (concatenation point)
                    for i in range(len(word) - 1):
                        if word[i].islower() and word[i+1].isupper():
                            word = word[i+1:]
                            break
                cleaned_words.append(word)
            player_name = ' '.join(cleaned_words)

            matches.append((player_name.strip(), yards_stat, match.start(), match.end()))

        rank = 1
        prev_end = 0
        player_entries = []

        for name_tuple in matches:
            player_name, yards_stat, match_start, match_end = name_tuple
            player_name = player_name.strip()

            # The details are between the previous match end and current match start
            if prev_end > 0:
                details_text = section_text[prev_end:match_start].strip()
                # Clean up details - remove Underdog's Pick'em references and excess whitespace
                details_text = re.sub(r"Underdog['\u2019]s Pick['\u2019]em\.?", '', details_text)
                details_text = re.sub(r'\s+', ' ', details_text).strip()
                # Remove leading periods and spaces
                details_text = details_text.lstrip('. ')

                if player_entries:
                    player_entries[-1]['Details'] = details_text

            # Match player name to player key
            player_id, standardized_name = match_player_name(player_name, player_key)

            player_entries.append({
                'Player Name': player_name,
                'Player ID': player_id,
                'Standardized Name': standardized_name,
                'Position': position,
                'Position Rank': rank,
                'Yards Stat': yards_stat,
                'Details': ''  # Will be filled by next iteration
            })

            prev_end = match_end
            rank += 1

        # Get details for the last player
        if player_entries and prev_end > 0:
            remaining_text = section_text[prev_end:].strip()
            # Look for the next player name pattern or end of section
            next_section = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z\'-]+)+)\s*-\s*[\d.]+\s+', remaining_text)
            if next_section:
                details_text = remaining_text[:next_section.start()].strip()
            else:
                # Take up to 1000 chars or until we hit another obvious section marker
                details_text = remaining_text[:1000].strip()

            details_text = re.sub(r"Underdog['\u2019]s Pick['\u2019]em\.?", '', details_text)
            details_text = re.sub(r'\s+', ' ', details_text).strip()
            # Remove leading periods and spaces
            details_text = details_text.lstrip('. ')
            player_entries[-1]['Details'] = details_text

        players_data.extend(player_entries)

    # Create DataFrame
    df = pd.DataFrame(players_data)
    return df
