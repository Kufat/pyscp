#!/usr/bin/env python3.9
import logging
import pyscp
import sys

logging.basicConfig(level=logging.DEBUG)

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} username password", file=sys.stderr)
    exit(1)

wiki = pyscp.wikidot.Wiki('https://scp-wiki.wikidot.com')
wiki.auth(sys.argv[1], sys.argv[2])
p = wiki('scp-series-2')
print(p.source)
