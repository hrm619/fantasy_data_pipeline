
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath("")))


# set standardized columns

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



fpts_cols = [
    'RK',
    'PLAYER NAME',
    'POS',
    'TEAM',
    'BYE',
    'ADP POS',
    'ADP',
    'FPTS',
    'G',
    'FPTS/G',
    'TIER',
    'PASS ATT',
    'PASS CMP',
    'PASS YDS',
    'PASS TD',
    'PASS INT',
    'RUSH ATT',
    'RUSH YDS',
    'RUSH TD',
    'REC REC',
    'REC YDS',
    'REC TD',
    'UP',
    'DOWN',
    'MOVE',
    'TARGET',
    'WIN'
]

fantasy_pros_cols = [
    'RK', 
    'TIER', 
    'PLAYER NAME', 
    'TEAM', 
    'POS', 
    'BYE', 
    'SOS', 
    'ECR VS ADP'
]

jj_cols = [
    'RK', 
    'PLAYER NAME', 
    'POS', 
    'POS RANK', 
    'TIER', 
    'AUCTION ($200)'
]


draftshark_ADP_cols = [
    'PLAYER NAME',
    'TEAM',
    'POS',
    'SLEEPER ADP',
    'MARKET INDEX',
    'DROP'
]


draftshark_rank_cols = [
    'PLAYER NAME',
    'POS',
    'TEAM',
    'G',
    'ADP',
    'BYE',
    'SOS',
    'INJURY RISK',
    'FLOOR PROJ',
    'CONS PROJ',
    'DS PROJ',
    'CEILING PROJ',
    '3D VALUE'
]

hayden_winks_cols = [
    'PLAYER NAME',
    'RK',
    'ADP',
    'DIFF',
    'FINISH-2024',
    'TEAM',
    'POS',
    'POS RANK',
    'NOTES',
    'ID'
]


cols_dict = {
    'fpts':fpts_cols,
    'fantasypros':fantasy_pros_cols,
    'jj':jj_cols,
    'draftshark_adp':draftshark_ADP_cols,
    'draftshark_rank':draftshark_rank_cols,
    'hayden_winks':hayden_winks_cols
}