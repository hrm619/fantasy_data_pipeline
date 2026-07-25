"""
Player name utilities for fantasy football data processing.

Functions for cleaning player names and managing player key mappings.
"""

import pandas as pd
import json
import os
import re
from typing import Dict, Any


# Generational suffixes sources disagree about. FantasyPros writes "James Cook III" /
# "Chris Godwin Jr" / "Kyle Pitts Sr" where DraftSharks, PFF and PFR write the bare name;
# player_key_dict.json carries BOTH conventions (54 names hold a suffix — "Patrick Mahomes
# II", "Odell Beckham Jr" — while others don't), so the mismatch runs in both directions.
#
# Note "I" is deliberately absent: nobody is listed as "Player I", and it would strip the
# trailing initial off a name like "Mister I".
_GENERATIONAL_SUFFIX = re.compile(r"\s+(?:II|III|IV|V|Jr|Sr)$", re.IGNORECASE)


def strip_generational_suffix(name: str) -> str:
    """Return `name` without a trailing generational suffix ('James Cook III' -> 'James Cook').

    Only used to build the fallback index in `add_player_ids` — never to rewrite the name a
    source reported.
    """
    return _GENERATIONAL_SUFFIX.sub("", str(name)).strip()


def build_suffix_fallback_index(player_name_to_key: Dict[str, str]) -> Dict[str, str]:
    """Index player IDs by suffix-stripped name, for names that resolve UNAMBIGUOUSLY.

    A base name claimed by two different IDs is dropped rather than guessed: real homonyms
    exist and PFR gives them distinct IDs (two Alex Smiths -> SmitAl02/SmitAl03, 8 such
    names here). Guessing between them is how a player inherits another's stats.
    """
    base_to_keys: Dict[str, set] = {}
    for name, key in player_name_to_key.items():
        base_to_keys.setdefault(strip_generational_suffix(name), set()).add(key)
    return {base: next(iter(keys)) for base, keys in base_to_keys.items() if len(keys) == 1}


# Marks an id this pipeline minted, not one sourced from Pro-Football-Reference.
PROVISIONAL_ID_PREFIX = "NEW:"


def mint_provisional_id(name: str) -> str:
    """Mint a provisional PLAYER ID for a player `player_key_dict.json` doesn't know.

    The dict is keyed by Pro-Football-Reference ids, which only exist once a player has NFL
    history — so every incoming rookie is absent from it. Since the board joins its sources on
    PLAYER ID, an id-less player can't be assembled at all and silently vanishes (this cost the
    entire 2026 rookie class its place: Jeremiyah Love at ECR 35, Carnell Tate at 64).

    The id is derived from the name alone, so every source mints the SAME id for the same
    player without coordination — that is what lets their rows join. It is deliberately NOT
    PFR-shaped: PFR's scheme has padding quirks ("CJ Ham" -> "HamxC.00") that make a guessed id
    a coin flip against colliding with a real player. The `NEW:` prefix keeps these obviously
    provisional, so when PFR assigns a real id after the player debuts you can reconcile
    deliberately rather than discovering a silent duplicate.

    Note punctuation is stripped but case is preserved: sources agree on Title Case, and
    `test_punctuation_does_not_split_a_player_across_sources` pins the punctuation half.
    """
    return PROVISIONAL_ID_PREFIX + re.sub(r"[^A-Za-z0-9]", "", str(name))


def is_provisional_id(player_id: Any) -> bool:
    """True if `player_id` was minted by `mint_provisional_id` rather than sourced from PFR."""
    return isinstance(player_id, str) and player_id.startswith(PROVISIONAL_ID_PREFIX)


def clean_player_names(df: pd.DataFrame, player_name_col: str = "PLAYER NAME") -> pd.DataFrame:
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
    df_clean[player_name_col] = df_clean[player_name_col].str.replace(r"\bJr\.", "Jr", regex=True)
    df_clean[player_name_col] = df_clean[player_name_col].str.replace(r"\bSr\.", "Sr", regex=True)

    # Remove all other special characters except spaces
    df_clean[player_name_col] = df_clean[player_name_col].str.replace(r"[^\w\s]", "", regex=True)

    # Clean up extra whitespace
    df_clean[player_name_col] = df_clean[player_name_col].str.strip().str.replace(r"\s+", " ", regex=True)

    return df_clean


def load_player_key_mapping(
    player_key_path: str, save_reverse_mapping: bool = True
) -> tuple[Dict[str, Any], Dict[str, str]]:
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

    with open(player_key_path, "r") as f:
        player_key_dict = json.load(f)

    # Create reverse mapping from player names to keys
    player_name_to_key = {}
    for key, value in player_key_dict.items():
        if isinstance(value, list):
            for name in value:
                player_name_to_key[name] = key
        else:
            player_name_to_key[value] = key

    # Optionally save reverse mapping for debugging/reference. Written beside the key file it
    # was derived from, NOT relative to the CWD: run from anywhere else and the old behaviour
    # scattered a stray `data/` directory wherever the process happened to start. For a repo-
    # root key file this resolves to exactly the same place as before.
    if save_reverse_mapping:
        key_dir = os.path.dirname(os.path.abspath(player_key_path))
        reverse_mapping_path = os.path.join(key_dir, "data", "player_name_to_key.json")
        os.makedirs(os.path.dirname(reverse_mapping_path), exist_ok=True)
        with open(reverse_mapping_path, "w") as f:
            json.dump(player_name_to_key, f, indent=4, sort_keys=True)

    return player_key_dict, player_name_to_key


def add_player_ids(
    df: pd.DataFrame,
    player_name_to_key: Dict[str, str],
    player_name_col: str = "PLAYER NAME",
    verbose: bool = True,
    mint_missing: bool = False,
) -> pd.DataFrame:
    """
    Add PLAYER ID column to dataframe using player name mapping.

    Matching is exact first. Names that match nothing then get a second lookup with their
    generational suffix stripped — sources disagree about those ("James Cook III" in
    FantasyPros vs "James Cook" everywhere else, and the reverse for "Patrick Mahomes II").
    An unmatched `fp` name is not a cosmetic miss: `fp` is the pipeline's only source of POS,
    and the board drops every row without one, so the player vanishes silently. This cost
    James Cook, Chris Godwin and Kyle Pitts their spot on the 2026 board.

    The fallback is strictly additive — exact matches are never overridden — and it declines
    ambiguous base names (see `build_suffix_fallback_index`).

    With `mint_missing`, whatever is still unmatched gets a provisional id derived from its
    name (see `mint_provisional_id`) instead of a null. This is what lets rookies onto the
    board at all: `player_key_dict.json` is keyed by PFR ids, which a player without NFL
    history simply does not have yet. It is opt-in because the stats aggregation deliberately
    relies on null ids to EXCLUDE unknown players from its joins — minting there would
    resurrect the null-join phantom-row bug in a new form.

    Args:
        df (pd.DataFrame): DataFrame to add player IDs to
        player_name_to_key (Dict[str, str]): Mapping from player names to IDs
        player_name_col (str): Name of the column containing player names
        verbose (bool): Whether to print match statistics
        mint_missing (bool): Mint a provisional id for names the dictionary doesn't know

    Returns:
        pd.DataFrame: DataFrame with PLAYER ID column added
    """
    df_with_ids = df.copy()
    # astype(object): when nothing matches, .map() yields an all-NaN float64 column and
    # writing ids into it is a dtype change pandas now warns on (and will later refuse).
    df_with_ids["PLAYER ID"] = df_with_ids[player_name_col].map(player_name_to_key).astype(object)

    unmatched = df_with_ids["PLAYER ID"].isna()
    if unmatched.any():
        fallback_index = build_suffix_fallback_index(player_name_to_key)
        recovered = df_with_ids.loc[unmatched, player_name_col].map(
            lambda n: fallback_index.get(strip_generational_suffix(n))
        )
        df_with_ids.loc[unmatched, "PLAYER ID"] = recovered

    minted = 0
    if mint_missing:
        still_unmatched = df_with_ids["PLAYER ID"].isna() & df_with_ids[player_name_col].notna()
        minted = int(still_unmatched.sum())
        if minted:
            df_with_ids.loc[still_unmatched, "PLAYER ID"] = df_with_ids.loc[still_unmatched, player_name_col].map(
                mint_provisional_id
            )

    if verbose:
        total_players = len(df_with_ids)
        matched_players = df_with_ids["PLAYER ID"].notna().sum()
        match_rate = matched_players / total_players * 100 if total_players > 0 else 0
        print(f"   Player ID matching: {matched_players}/{total_players} players matched ({match_rate:.1f}%)")
        suffix_matches = int(unmatched.sum() - df_with_ids.loc[unmatched, "PLAYER ID"].isna().sum()) - minted
        if suffix_matches:
            print(f"      ({suffix_matches} matched by normalizing a generational suffix)")
        if minted:
            print(
                f"      ({minted} unknown to player_key_dict.json — minted a provisional '{PROVISIONAL_ID_PREFIX}' id)"
            )

    return df_with_ids
