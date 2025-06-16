#!/usr/bin/env python3
"""
Comprehensive Quality Analysis of PDF-to-Markdown Conversion
"""

import os
import json
import re
from pathlib import Path
from collections import Counter

def analyze_tables_in_content(content):
    """Analyze table quality in markdown content."""
    # Find table blocks
    table_blocks = []
    lines = content.split('\n')
    current_table = []
    in_table = False
    
    for line in lines:
        if '|' in line and line.strip().startswith('|'):
            if not in_table:
                in_table = True
                current_table = []
            current_table.append(line.strip())
        else:
            if in_table and current_table:
                table_blocks.append('\n'.join(current_table))
                current_table = []
            in_table = False
    
    # Add last table if exists
    if current_table:
        table_blocks.append('\n'.join(current_table))
    
    valid_tables = 0
    table_details = []
    
    for i, table_block in enumerate(table_blocks):
        table_lines = [line for line in table_block.split('\n') if line.strip()]
        
        if len(table_lines) < 2:
            continue
        
        # Count columns in first row
        first_row = table_lines[0]
        cols = len([col for col in first_row.split('|') if col.strip()])
        
        # Check for header separator
        has_separator = False
        if len(table_lines) > 1:
            second_line = table_lines[1]
            has_separator = '-' in second_line or '=' in second_line
        
        # Determine if table is valid
        is_valid = (
            cols >= 2 and
            len(table_lines) >= 2 and
            (has_separator or len(table_lines) >= 3)
        )
        
        if is_valid:
            valid_tables += 1
        
        table_details.append({
            'rows': len(table_lines),
            'cols': cols,
            'has_separator': has_separator,
            'valid': is_valid,
            'preview': first_row[:60] + '...' if len(first_row) > 60 else first_row
        })
    
    return len(table_blocks), valid_tables, table_details

def analyze_file_structure(content):
    """Analyze the structure of the markdown content."""
    lines = content.split('\n')
    
    sections = 0
    images = 0
    citations = 0
    equations = 0
    lists = 0
    
    for line in lines:
        # Count headers
        if line.startswith('#'):
            sections += 1
        
        # Count images
        images += len(re.findall(r'!\[.*?\]', line))
        
        # Count citations (basic patterns)
        citations += len(re.findall(r'\[.*?\d+.*?\]', line))
        citations += len(re.findall(r'\(.*?\d{4}.*?\)', line))
        
        # Count equations
        equations += len(re.findall(r'\$.*?\$', line))
        
        # Count list items
        if line.strip().startswith(('- ', '* ', '+ ')) or re.match(r'^\s*\d+\.', line.strip()):
            lists += 1
    
    return {
        'sections': sections,
        'images': images,
        'citations': citations,
        'equations': equations,
        'lists': lists
    }

def main():
    print("PDF-to-Markdown Conversion Quality Analysis")
    print("=" * 50)
    
    out_dir = Path('out/md-json')
    if not out_dir.exists():
        print(f"Directory {out_dir} not found!")
        return
    
    md_files = list(out_dir.glob('*.md'))
    print(f"Analyzing {len(md_files)} markdown files...")
    print()
    
    total_size = 0
    total_tables = 0
    total_valid_tables = 0
    all_analyses = []
    
    # Analyze each file
    for md_file in sorted(md_files):
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        size_kb = len(content) / 1024
        total_size += size_kb
        
        # Analyze tables
        table_count, valid_count, table_details = analyze_tables_in_content(content)
        total_tables += table_count
        total_valid_tables += valid_count
        
        # Analyze structure
        structure = analyze_file_structure(content)
        
        analysis = {
            'file': md_file.name,
            'size_kb': size_kb,
            'tables': table_count,
            'valid_tables': valid_count,
            'validity_rate': valid_count / table_count if table_count > 0 else 0,
            'structure': structure,
            'table_details': table_details
        }
        
        all_analyses.append(analysis)
        
        print(f"{md_file.name[:50]:<50} {size_kb:6.1f}KB  {table_count:3d} tables  {valid_count:3d} valid ({analysis['validity_rate']:.1%})")
    
    print()
    print("=" * 50)
    print("SUMMARY STATISTICS")
    print("=" * 50)
    
    overall_validity = total_valid_tables / total_tables if total_tables > 0 else 0
    
    print(f"Total files:           {len(md_files)}")
    print(f"Total content size:    {total_size:.1f} KB")
    print(f"Average file size:     {total_size/len(md_files):.1f} KB")
    print(f"Total tables found:    {total_tables}")
    print(f"Valid tables:          {total_valid_tables}")
    print(f"Overall validity rate: {overall_validity:.1%}")
    
    # File size statistics
    sizes = [a['size_kb'] for a in all_analyses]
    print(f"File size range:       {min(sizes):.1f} - {max(sizes):.1f} KB")
    
    # Content statistics
    total_sections = sum(a['structure']['sections'] for a in all_analyses)
    total_images = sum(a['structure']['images'] for a in all_analyses)
    total_citations = sum(a['structure']['citations'] for a in all_analyses)
    
    print(f"Total sections:        {total_sections}")
    print(f"Total images:          {total_images}")
    print(f"Total citations:       {total_citations}")
    
    print()
    print("FILES WITH ISSUES:")
    print("-" * 30)
    
    # Identify problematic files
    issues_found = False
    for analysis in all_analyses:
        issues = []
        
        if analysis['size_kb'] < 20:
            issues.append("Small file")
        
        if analysis['tables'] == 0:
            issues.append("No tables")
        elif analysis['validity_rate'] < 0.8:
            issues.append(f"Low table quality ({analysis['validity_rate']:.1%})")
        
        if analysis['structure']['sections'] < 3:
            issues.append("Few sections")
        
        if issues:
            issues_found = True
            print(f"{analysis['file'][:45]:<45} {', '.join(issues)}")
    
    if not issues_found:
        print("No significant issues found!")
    
    print()
    print("RECOMMENDATIONS:")
    print("-" * 20)
    
    if overall_validity < 0.9:
        print("- Consider improving table extraction algorithms")
    
    small_files = [a for a in all_analyses if a['size_kb'] < 30]
    if small_files:
        print(f"- Review {len(small_files)} small files for incomplete extraction")
    
    no_table_files = [a for a in all_analyses if a['tables'] == 0]
    if no_table_files:
        print(f"- Check {len(no_table_files)} files with no tables")
    
    print(f"- Overall quality: {'EXCELLENT' if overall_validity > 0.95 else 'GOOD' if overall_validity > 0.85 else 'NEEDS IMPROVEMENT'}")

if __name__ == '__main__':
    main()
