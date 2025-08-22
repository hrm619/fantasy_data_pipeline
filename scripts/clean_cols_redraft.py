
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
    'RK',
    'PLAYER NAME',
    'POS',
    'TEAM',
    'BYE',
    'TIER',
    'EXODIA'
]

# fantasy pros
fp_cols = [
    'ECR', 
    'TIER', 
    'PLAYER NAME', 
    'TEAM', 
    'POS', 
    'BYE',
    'SOS',
    'ECR VS ADP'
]

# jj zacharaiason
jj_cols = [
    'RK',
    'PLAYER NAME', 
    'POS',
    'POS RANK',
    'TIER',
    'AUCTION'
]

# draft sharks
ds_cols = [
    'RK',
    'TEAM',
    'PLAYER NAME',
    'POS',
    'G',
    'DS ADP',
    'BYE',
    'SOS',
    'INJURY RISK',
    'FLOOR PROJ',
    'CONS PROJ',
    'DS PROJ',
    'CEILING PROJ',
    '3D VALUE'
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

# pff
pff_cols = [
    'RK',
    'PLAYER NAME',
    'TEAM',
    'POS',
    'POS RANK',
    'BYE',
    'PFF ADP',
    'PROJ',
    'AUCTION'
]

# adp
adp_cols = [
    'PLAYER NAME',
    'TEAM',
    'BYE',
    'POS',
    'ADP',
    'MARKET INDEX',
    'RT'
]


# file mapping
file_lookup = { 
    "fpts":"Scott Barrett",
    "fp":"FantasyPros", 
    "jj":"1QBRankings_",
    "ds":"rankings-half-ppr",
    "hw":"tableDownload",
    "pff":"Draft-rankings-export",
    "adp":"adp-rankings"}

# cols dictionary
cols_dict = {
    'fpts':fpts_cols,
    'fp':fp_cols,
    'jj':jj_cols,
    'ds':ds_cols,
    'hw':hw_cols,
    'pff':pff_cols,
    'adp':adp_cols
}

