# Fantasy Football Data Scraper

A Python web scraper that extracts fantasy football data from Pro Football Reference.

## Features

- Scrapes fantasy football rankings from [Pro Football Reference](https://www.pro-football-reference.com/years/2024/fantasy.htm)
- Converts data to pandas DataFrame
- Saves data to CSV format
- Includes error handling and user-agent headers
- Simple and easy to use

## Installation

1. Install dependencies using uv (recommended):
```bash
uv pip install -r requirements.txt
```

Or using pip:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```python
from scripts.fantasy_scraper import scrape_fantasy_data

# Scrape the default URL (2024 fantasy data)
df = scrape_fantasy_data()

if df is not None:
    print(f"Scraped {len(df)} players")
    print(df.head())
```

### Custom URL

```python
# Scrape a different year or page
df = scrape_fantasy_data("https://www.pro-football-reference.com/years/2023/fantasy.htm")
```

### Save to CSV

```python
from scripts.fantasy_scraper import scrape_fantasy_data, save_fantasy_data

df = scrape_fantasy_data()
if df is not None:
    save_fantasy_data(df, "my_fantasy_data.csv")
```

### Run Example

```bash
cd scripts
python example_usage.py
```

## Data Structure

The scraper extracts the following information for each player:
- Player name
- Team
- Position
- Age
- Games played/started
- Passing stats (completions, attempts, yards, TDs, INTs)
- Rushing stats (attempts, yards, TDs)
- Receiving stats (targets, receptions, yards, TDs)
- Fumbles
- Scoring
- Fantasy points (standard, PPR, DraftKings, FanDuel)
- Position rank and overall rank

## Files

- `scripts/fantasy_scraper.py` - Main scraping function
- `scripts/example_usage.py` - Example usage script
- `requirements.txt` - Python dependencies
- `data/` - Directory where scraped data is saved

## Notes

- The scraper uses proper headers to avoid being blocked
- Includes timeout handling for network requests
- Handles missing data gracefully
- Respects the website's robots.txt and terms of service
- Consider adding delays between requests if scraping multiple pages

## Dependencies

- `requests` - HTTP library for making web requests
- `lxml` - XML/HTML parser for extracting data
- `pandas` - Data manipulation and analysis 