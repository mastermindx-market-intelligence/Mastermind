from pathlib import Path
import argparse
import re

parser = argparse.ArgumentParser()
parser.add_argument('--inline-output', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parent
parts = []
for name in ('fixture.mjs', 'renderer.mjs', 'controller.mjs'):
    text = (root / name).read_text()
    text = re.sub(r'^import .*?;\n', '', text, flags=re.M)
    text = re.sub(r'^export ', '', text, flags=re.M)
    parts.append(text)
script = '\n'.join(parts)
bootstrap = '''
const root = document.getElementById('mmx-swarm-atlas');
try { mountAtlas(root); }
catch (error) {
 root.dataset.sourceState = 'renderer-unavailable';
 root.querySelector('[data-field="status"]').textContent = 'RENDERING UNAVAILABLE';
 root.querySelector('[data-field="current"]').textContent = 'The visual renderer could not start in this browser.';
 for (const control of root.querySelectorAll('button, select, input')) control.disabled = true;
}
'''
fragment = (root / 'surface.html').read_text() + '\n<script>\n(()=>{\n' + script + bootstrap + '\n})();\n</script>\n'
if args.inline_output:
    args.inline_output.write_text(fragment)
standalone = '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Mastermind Living Atlas — Swarm Study</title><style>body{margin:0;padding:20px;background:#03060a;}main{max-width:1440px;margin:0 auto;}@media(max-width:600px){body{padding:0;}}</style></head><body><main>' + fragment + '</main></body></html>\n'
(root / 'index.html').write_text(standalone)
print({'fragment_bytes': len(fragment.encode()), 'standalone_bytes': len(standalone.encode())})
