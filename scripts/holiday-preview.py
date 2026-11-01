#!/usr/bin/env python3
"""Offline calendar prompt preview. No GPU/apply options are accepted."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from holiday_preview import fixture_preview

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--date',required=True)
parser.add_argument('--timezone',default='America/Chicago')
parser.add_argument('--country',default='US')
parser.add_argument('--subdivision',default='')
parser.add_argument('--scene',choices=['town','urban','rural','woodland','river','townpark'],default='town')
parser.add_argument('--width',type=int,default=1080)
parser.add_argument('--height',type=int,default=1920)
parser.add_argument('--latitude',type=float,default=41.8,help='Illustrative default; not device geolocation')
parser.add_argument('--longitude',type=float,default=-90.5,help='Illustrative default; not device geolocation')
args=parser.parse_args()
try:
    print(json.dumps(fixture_preview(args.date,{'timezone':args.timezone,'country_code':args.country,'subdivision_code':args.subdivision,'latitude':args.latitude,'longitude':args.longitude},scene='urban' if args.scene=='town' else args.scene,width=args.width,height=args.height),indent=2))
except (ValueError,KeyError) as error:
    parser.error(str(error))
