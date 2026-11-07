#!/usr/bin/env python3
from pathlib import Path
import json, sys
root=Path(__file__).resolve().parents[1]
required=[
  'SKILL.md','README.md','manifest.json','tokens/mastermind.tokens.json','tokens/mastermind.css',
  'references/foundations.md','references/components.md','references/archetypes.md',
  'references/states-accessibility.md','references/paper-sources.md','references/sources.md','examples/patterns.md'
]
missing=[p for p in required if not (root/p).exists()]
if missing:
    print('FAIL missing:', ', '.join(missing)); sys.exit(1)
skill=(root/'SKILL.md').read_text()
if not skill.startswith('---\n') or 'name: mastermind-design-system' not in skill or 'description:' not in skill.split('---',2)[1]:
    print('FAIL invalid SKILL.md frontmatter'); sys.exit(1)
data=json.loads((root/'tokens/mastermind.tokens.json').read_text())
names=[x['name'] for x in data['tokens']]
if len(names)!=len(set(names)):
    print('FAIL duplicate token names'); sys.exit(1)
for n in ['--mx-dark-bg','--mx-light-bg','--fs-display','--sp-8','--r-panel','--mx-dark-tier-ink','--mx-light-tier-ink']:
    if n not in names:
        print('FAIL required token absent:', n); sys.exit(1)
print(f'PASS: {len(required)} required files; {len(names)} portable tokens; skill frontmatter valid')
