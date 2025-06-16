#!/usr/bin/env python3
"""Simple analysis of converted files"""

import os
from pathlib import Path

def main():
    out_dir = Path('out/md-json')
    print(f"Checking directory: {out_dir}")
    
    if not out_dir.exists():
        print(f"Directory {out_dir} not found!")
        return
    
    md_files = list(out_dir.glob('*.md'))
    print(f"Found {len(md_files)} markdown files")
    
    total_size = 0
    total_tables = 0
    
    for md_file in md_files:
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        size_kb = len(content) / 1024
        tables = content.count('|')
        total_size += size_kb
        total_tables += tables
        
        print(f"{md_file.name}: {size_kb:.1f}KB, ~{tables} table chars")
    
    print(f"\nTotal: {total_size:.1f}KB, {total_tables} table characters")

if __name__ == '__main__':
    main()
