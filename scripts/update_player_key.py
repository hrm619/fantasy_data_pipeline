
import sys
import os
import json
from difflib import get_close_matches

sys.path.append(os.path.dirname(os.path.abspath("")))

# update the player key dict with similar names

def update_player_key_dict(dfs, likely_player_name_columns, player_key_dict_path="../player_key_dict.json", similarity_cutoff=0.95):
    """
    Args:
        dfs (list of pandas.DataFrame): List of DataFrames containing player data.
        likely_player_name_columns (list of str): List of column names (one per DataFrame) that likely contain player names.
        player_key_dict_path (str, optional): Path to the JSON file containing the player key dictionary. Default is "player_key_dict.json".
        similarity_cutoff (float, optional): Similarity threshold (between 0 and 1) for matching player names. Default is 0.9.

    For each DataFrame and its likely player name column, check if each player name exists in the player_key_dict values.
    If not, find the most similar value and add the new name as an alias to the corresponding key-value pair.
    """

    # Load the player_key_dict
    with open(player_key_dict_path, "r") as f:
        player_key_dict = json.load(f)

    # Build a reverse mapping: name -> key(s)
    name_to_keys = {}
    for k, v in player_key_dict.items():
        # If value is a list, flatten
        if isinstance(v, list):
            for name in v:
                name_to_keys.setdefault(name, []).append(k)
        else:
            name_to_keys.setdefault(v, []).append(k)

    # Get all known player names (flattened)
    known_names = set(name_to_keys.keys())

    # Track changes to avoid duplicates
    changes = {}

    for df, col in zip(dfs, likely_player_name_columns):
        for name in df[col].dropna().unique():
            if name in known_names:
                continue  # Already present
            # Find the closest match
            matches = get_close_matches(name, known_names, n=1, cutoff=similarity_cutoff)
            if matches:
                best_match = matches[0]
                # Find the key(s) for this match
                keys = name_to_keys[best_match]
                for key in keys:
                    # Update the value in player_key_dict to be a list of names
                    val = player_key_dict[key]
                    if isinstance(val, list):
                        if name not in val:
                            player_key_dict[key].append(name)
                            changes.setdefault(key, []).append(name)
                    else:
                        if name != val:
                            player_key_dict[key] = [val, name]
                            changes.setdefault(key, []).append(name)
                print(f"Added alias '{name}' to key(s) {keys} (matched '{best_match}')")
            else:
                # If no close match is found, create a new key using the player name:
                # key = last name + first name, value = player name string.
                parts = name.split()
                if len(parts) >= 2:
                    last_name = parts[1]
                    first_name = parts[0]
                    new_key = f"{last_name}{first_name}"
                else:
                    # If only one part, use it as both last and first name
                    new_key = f"{parts[0]}{parts[0]}"
                # Ensure the key is unique
                orig_key = new_key
                counter = 1
                while new_key in player_key_dict:
                    new_key = f"{orig_key}{counter}"
                    counter += 1
                player_key_dict[new_key] = name
                changes.setdefault(new_key, []).append(name)
                print(f"No close match found for '{name}'. Added new key '{new_key}' with value '{name}'")

    # Save the updated dict if there were changes
    if changes:
        with open(player_key_dict_path, "w") as f:
            json.dump(player_key_dict, f, indent=2)
        print(f"Updated player_key_dict.json with new aliases: {changes}")
    else:
        print("No new aliases added.")

# Example usage:
# update_player_key_dict_with_similar_names(dfs, likely_player_name_columns)

