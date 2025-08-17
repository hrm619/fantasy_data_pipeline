
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath("")))


# set standardized columns

# football reference
football_ref_cols = [
    'NUMBER',
    'PLAYER NAME',
    'TEAM',
    'POS',
    'AGE',
    'G',
    'GS', 
    'PASS COMP',
    'PASS ATT',
    'PASS YDS',
    'PASS TD',
    'PASS INT',
    'RUSH ATT',
    'RUSH YDS',
    'RUSH Y/A',
    'RUSH TD',
    'REC TGT',
    'REC REC',
    'REC YDS',
    'REC Y/R',
    'REC TD',
    'FMB',
    'FL',
    'TD',
    '2PM',
    '2PP',
    'FANTPT',
    'PPR',
    'DKPT',
    'FDPT',
    'VBD',
    'POS RANK',
    'RK',
    'PLAYER ID'
]

# football reference draft
football_ref_draft_cols = [
    'ROUND',
    'PICK',
    'TEAM',
    'PLAYER NAME',
    'POS',
    'AGE',
    'TO TEAM',
    'AP1',
    'PB',
    'ST',
    'wAV',
    'DrAV',
    'G',
    'Cmp',
    'Att',
    'Yds',
    'TD',
    'Int',
    'Att.1',
    'Yds.1',
    'TD.1',
    'Rec',
    'Yds.2',
    'TD.2',
    'Solo',
    'Int.1',
    'Sk',
    'College/Univ',
    'NONE',
    'PLAYER ID'
 ]


# fantasy points data
fpts_cols = [
    'ID',
    'ID NUMBER',
    'PLAYER NAME',
    'POS',
    'TEAM',
    'RK',
    'POSITION',
    'ADP'
]

# fantasy pros
fp_cols = [
    'ECR', 
    'TIER', 
    'PLAYER NAME', 
    'TEAM', 
    'POS', 
    'BYE',
    'ECR VS ADP'
]

# jj zacharaiason
jj_cols = [
    'ID',
    'PLAYER NAME', 
    'POS', 
    'ADP',
    'TEAM'
]

# draft sharks
ds_cols = [
    'PLAYER NAME',
    'POS',
    'TEAM',
    'UNDERDOG ADP',
    'BYE',
    'CONS PROJ',
    'FLOOR PROJ',
    'DS PROJ',
    'CEILING PROJ',
    '3D VALUE',
    'DROP',
    'DROP 2'
]

# hayden winks
hw_cols = [
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
]

# file mapping
file_lookup = { 
    "fpts":"BestBallRankingsDraftKings",
    "fp":"FantasyPros", 
    "jj":"DKRankings",
    "ds":"dynasty-rankings",
    "hw":"tableDownload"}

# cols dictionary
cols_dict = {
    'fpts':fpts_cols,
    'fp':fp_cols,
    'jj':jj_cols,
    'ds':ds_cols,
    'hw':hw_cols
}

