#!/usr/bin/env python3
"""
Comprehensive Analysis of PDF-to-Markdown Conversion Results
Analyzes all converted files in out/md-json for quality assessment
"""

import os
import json
import re
from pathlib import Path
from collections import defaultdict, Counter
import pandas as pd

def analyze_markdown_file(md_path):
    """Analyze a single markdown file for various quality metrics."""
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    analysis = {
        'file': os.path.basename(md_path),
        'size_kb': len(content) / 1024,
        'total_lines': len(content.split('\n')),
        'sections': 0,
        'tables': 0,
        'images': 0,
        'citations': 0,
        'equations': 0,
        'code_blocks': 0,
        'list_items': 0,
        'bold_text': 0,
        'italic_text': 0,
        'links': 0,
        'table_details': [],
        'section_hierarchy': [],
        'quality_issues': []
    }
    
    lines = content.split('\n')
    
    # Count various markdown elements
    for line in lines:
        # Headers/Sections
        if line.startswith('#'):
            analysis['sections'] += 1
            level = len(line) - len(line.lstrip('#'))
            section_text = line.lstrip('# ').strip()
            analysis['section_hierarchy'].append((level, section_text))
        
        # Tables
        if '|' in line and line.strip().startswith('|'):
            analysis['tables'] += 1
        
        # Images
        if '![' in line:
            analysis['images'] += len(re.findall(r'!\[.*?\]', line))
        
        # Citations (various formats)
        analysis['citations'] += len(re.findall(r'\[.*?\]\(.*?\)', line))  # [text](url)
        analysis['citations'] += len(re.findall(r'\[\d+\]', line))  # [1]
        analysis['citations'] += len(re.findall(r'\(.*?\d{4}.*?\)', line))  # (Author, 2023)
        
        # Equations
        if '$' in line:
            analysis['equations'] += len(re.findall(r'\$.*?\$', line))
        
        # Code blocks
        if line.strip().startswith('```'):
            analysis['code_blocks'] += 1
        
        # Lists
        if line.strip().startswith(('- ', '* ', '+ ')) or re.match(r'^\s*\d+\.', line.strip()):
            analysis['list_items'] += 1
        
        # Bold text
        analysis['bold_text'] += len(re.findall(r'\*\*.*?\*\*', line))
        
        # Italic text
        analysis['italic_text'] += len(re.findall(r'\*.*?\*', line))
        
        # Links
        analysis['links'] += len(re.findall(r'\[.*?\]\(.*?\)', line))
    
    # Analyze table quality
    table_blocks = re.findall(r'\|.*?\n(?:\|.*?\n)*', content, re.MULTILINE)
    valid_tables = 0
    
    for i, table_block in enumerate(table_blocks):
        table_lines = [line.strip() for line in table_block.strip().split('\n') if line.strip()]
        
        if len(table_lines) < 2:
            continue
            
        # Check if it's a valid table structure
        first_line_cols = len([col for col in table_lines[0].split('|') if col.strip()])
        has_separator = len(table_lines) > 1 and '-' in table_lines[1]
        
        table_info = {
            'index': i + 1,
            'rows': len(table_lines),
            'cols': first_line_cols,
            'has_header_separator': has_separator,
            'content_preview': table_lines[0][:100] + '...' if len(table_lines[0]) > 100 else table_lines[0]
        }
        
        # Check for common table quality issues
        if first_line_cols < 2:
            table_info['issue'] = 'Too few columns'
        elif not has_separator and len(table_lines) > 1:
            table_info['issue'] = 'Missing header separator'
        elif len(table_lines) < 3:
            table_info['issue'] = 'Too few rows'
        else:
            table_info['issue'] = 'Valid'
            valid_tables += 1
        
        analysis['table_details'].append(table_info)
    
    analysis['valid_tables'] = valid_tables
    analysis['table_validity_rate'] = valid_tables / len(table_blocks) if table_blocks else 0
    
    # Quality issues detection
    if analysis['size_kb'] < 10:
        analysis['quality_issues'].append('File too small (< 10KB)')
    
    if analysis['sections'] < 3:
        analysis['quality_issues'].append('Too few sections')
    
    if analysis['tables'] == 0:
        analysis['quality_issues'].append('No tables found')
    
    if analysis['table_validity_rate'] < 0.8:
        analysis['quality_issues'].append(f'Low table validity rate: {analysis["table_validity_rate"]:.1%}')
    
    # Check for extraction artifacts
    if 'Error:' in content or 'Failed to' in content:
        analysis['quality_issues'].append('Contains error messages')
    
    return analysis

def analyze_json_metadata(json_path):
    """Analyze JSON metadata for completeness."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        analysis = {
            'has_title': bool(metadata.get('title')),
            'has_authors': bool(metadata.get('authors')),
            'has_abstract': bool(metadata.get('abstract')),
            'has_keywords': bool(metadata.get('keywords')),
            'has_doi': bool(metadata.get('doi')),
            'sections_count': len(metadata.get('sections', [])),
            'references_count': len(metadata.get('references', [])),
            'tables_count': len(metadata.get('tables', [])),
            'figures_count': len(metadata.get('figures', []))
        }
        
        analysis['completeness_score'] = sum([
            analysis['has_title'],
            analysis['has_authors'],
            analysis['has_abstract'],
            analysis['has_keywords'],
            analysis['sections_count'] > 0,
            analysis['references_count'] > 0
        ]) / 6
        
        return analysis
    except Exception as e:
        return {'error': str(e)}

def main():
    """Run comprehensive analysis on all converted files."""
    out_dir = Path('out/md-json')
    
    if not out_dir.exists():
        print(f"Output directory {out_dir} not found!")
        return
    
    print("🔍 Comprehensive Analysis of PDF-to-Markdown Conversion Results")
    print("=" * 70)
    
    # Get all markdown files
    md_files = list(out_dir.glob('*.md'))
    
    if not md_files:
        print("No markdown files found!")
        return
    
    print(f"Found {len(md_files)} markdown files to analyze")
    print()
    
    # Analyze each file
    analyses = []
    total_tables = 0
    total_valid_tables = 0
    
    for md_file in sorted(md_files):
        print(f"Analyzing: {md_file.name}")
        
        # Analyze markdown
        md_analysis = analyze_markdown_file(md_file)
        
        # Analyze corresponding JSON metadata
        json_file = md_file.with_suffix('.json')
        if json_file.exists():
            json_analysis = analyze_json_metadata(json_file)
            md_analysis['metadata'] = json_analysis
        
        analyses.append(md_analysis)
        total_tables += len(md_analysis['table_details'])
        total_valid_tables += md_analysis['valid_tables']
    
    print("\n" + "=" * 70)
    print("📊 SUMMARY STATISTICS")
    print("=" * 70)
    
    # Overall statistics
    total_size = sum(a['size_kb'] for a in analyses)
    total_sections = sum(a['sections'] for a in analyses)
    total_images = sum(a['images'] for a in analyses)
    total_citations = sum(a['citations'] for a in analyses)
    
    print(f"Total files analyzed: {len(analyses)}")
    print(f"Total content size: {total_size:.1f} KB")
    print(f"Average file size: {total_size/len(analyses):.1f} KB")
    print(f"Total sections: {total_sections}")
    print(f"Total images: {total_images}")
    print(f"Total citations: {total_citations}")
    print(f"Total tables found: {total_tables}")
    print(f"Valid tables: {total_valid_tables}")
    print(f"Table validity rate: {total_valid_tables/total_tables*100:.1f}%" if total_tables > 0 else "N/A")
    
    # File size distribution
    sizes = [a['size_kb'] for a in analyses]
    print(f"\nFile size distribution:")
    print(f"  Min: {min(sizes):.1f} KB")
    print(f"  Max: {max(sizes):.1f} KB")
    print(f"  Median: {sorted(sizes)[len(sizes)//2]:.1f} KB")
    
    # Quality issues summary
    all_issues = []
    for a in analyses:
        all_issues.extend(a['quality_issues'])
    
    if all_issues:
        print(f"\n⚠️  Quality Issues Summary:")
        issue_counts = Counter(all_issues)
        for issue, count in issue_counts.most_common():
            print(f"  {issue}: {count} files")
    
    print("\n" + "=" * 70)
    print("📋 DETAILED FILE ANALYSIS")
    print("=" * 70)
    
    # Detailed analysis per file
    for analysis in sorted(analyses, key=lambda x: x['size_kb'], reverse=True):
        print(f"\n📄 {analysis['file']}")
        print(f"   Size: {analysis['size_kb']:.1f} KB | Sections: {analysis['sections']} | Tables: {len(analysis['table_details'])} | Valid: {analysis['valid_tables']}")
        
        if analysis['quality_issues']:
            print(f"   ⚠️  Issues: {', '.join(analysis['quality_issues'])}")
        
        # Show metadata completeness if available
        if 'metadata' in analysis and 'completeness_score' in analysis['metadata']:
            score = analysis['metadata']['completeness_score']
            print(f"   📊 Metadata completeness: {score:.1%}")
        
        # Show problematic tables
        problematic_tables = [t for t in analysis['table_details'] if t.get('issue') != 'Valid']
        if problematic_tables:
            print(f"   🔍 Problematic tables: {len(problematic_tables)}")
            for table in problematic_tables[:3]:  # Show first 3
                print(f"      Table {table['index']}: {table['issue']} ({table['rows']}x{table['cols']})")
            if len(problematic_tables) > 3:
                print(f"      ... and {len(problematic_tables) - 3} more")
    
    print("\n" + "=" * 70)
    print("🎯 RECOMMENDATIONS")
    print("=" * 70)
    
    # Generate recommendations
    avg_validity = total_valid_tables / total_tables if total_tables > 0 else 0
    
    if avg_validity < 0.9:
        print("• Table extraction could be improved - consider refining regex patterns")
    
    small_files = [a for a in analyses if a['size_kb'] < 20]
    if small_files:
        print(f"• {len(small_files)} files are quite small - check if content extraction is complete")
    
    no_table_files = [a for a in analyses if len(a['table_details']) == 0]
    if no_table_files:
        print(f"• {len(no_table_files)} files have no tables - verify if this is expected")
    
    files_with_issues = [a for a in analyses if a['quality_issues']]
    if files_with_issues:
        print(f"• {len(files_with_issues)} files have quality issues that should be reviewed")
    
    print(f"\n✅ Overall conversion quality appears {'excellent' if avg_validity > 0.95 else 'good' if avg_validity > 0.8 else 'needs improvement'}")
    print(f"📈 Success rate: {(len(analyses) - len(files_with_issues)) / len(analyses):.1%}")

if __name__ == '__main__':
    main()
