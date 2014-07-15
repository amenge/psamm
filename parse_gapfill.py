#!/usr/bin/env python

'''Parse GapFill output and print added reactions

The GapFill file should be produced with parameter "ps=0".
'''

import csv
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse GapFill output')
    parser.add_argument('gapfill', type=argparse.FileType('r'), help='GapFill output file (ps=0)')
    
    args = parser.parse_args()

    # Parse out added reactions
    flag = False
    gffile = args.gapfill
    for line in gffile:
        if line.startswith('---- VAR yd'):
            flag = True
            for i in range(3):
                next(gffile)
        elif flag:
            if line == '\n':
                break

            fields = line.split()
            
            rxn_id = fields[0]
            enabled = fields[2] != '.'
            if enabled:
                print '{}\tadded'.format(rxn_id)
                
    # Parse out reversed reactions
    flag = False
    gffile.seek(0)
    for line in gffile:
        if line.startswith('---- VAR ym'):
            flag = True
            for i in range(3):
                next(gffile)
        elif flag:
            if line == '\n':
                break

            fields = line.split()
            
            rxn_id = fields[0]
            enabled = fields[2] != '.'
            if enabled:
                print '{}\treverse'.format(rxn_id)
        
            
    gffile.close()
