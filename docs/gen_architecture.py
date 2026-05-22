"""
Generate docs/architecture.png — run with: py docs/gen_architecture.py
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ── Palette ──────────────────────────────────────────────────────────────────
BG     = '#0d1117'
CARD   = '#161b22'
BORDER = '#30363d'
PRI    = '#e6edf3'
SEC    = '#8b949e'
ARROW  = '#58a6ff'

C = {
    'event':   '#a78bfa',   # EventBridge  – purple
    'lambda':  '#fb923c',   # Lambda       – orange
    's3':      '#4ade80',   # S3           – green
    'bedrock': '#fbbf24',   # Bedrock / AI – amber
    'catalog': '#38bdf8',   # Glue + Athena– sky blue
    'dash':    '#f87171',   # Dashboard    – red
}

# ── Figure ───────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(16, 8), facecolor=BG, dpi=160)
ax  = fig.add_axes([0, 0, 1, 1], facecolor=BG)
ax.set_xlim(0, 16)
ax.set_ylim(0, 8)
ax.axis('off')

# ── Helpers ──────────────────────────────────────────────────────────────────
def draw_box(cx, cy, w, h, title, sub, color):
    x, y = cx - w / 2, cy - h / 2
    # shadow
    ax.add_patch(FancyBboxPatch(
        (x + .06, y - .06), w, h,
        boxstyle='round,pad=0.07', facecolor='#000000',
        edgecolor='none', alpha=.35, zorder=2))
    # card
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle='round,pad=0.07', facecolor=CARD,
        edgecolor=color, linewidth=1.8, zorder=3))
    # left accent bar
    ax.add_patch(FancyBboxPatch(
        (x, y + .08), .11, h - .16,
        boxstyle='round,pad=0.02', facecolor=color,
        edgecolor='none', alpha=.95, zorder=4))
    # text
    top_y = cy + .14 if sub else cy
    ax.text(cx + .08, top_y, title,
            ha='center', va='center', fontsize=8.5, fontweight='bold',
            color=PRI, family='monospace', zorder=5)
    if sub:
        ax.text(cx + .08, cy - .2, sub,
                ha='center', va='center', fontsize=7,
                color=SEC, family='monospace', zorder=5)

def draw_arrow(x1, y1, x2, y2, label='', rad=0):
    ax.annotate(
        '', xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle='-|>', color=ARROW, lw=1.5,
            mutation_scale=11,
            connectionstyle=f'arc3,rad={rad}'),
        zorder=6)
    if label:
        mx = (x1 + x2) / 2 + (.6 * rad if rad else 0)
        my = (y1 + y2) / 2 + (.18 if abs(x1 - x2) < .2 else .14)
        ax.text(mx, my, label, ha='center', va='center',
                fontsize=6.5, color=SEC, family='monospace', zorder=7,
                bbox=dict(facecolor=BG, edgecolor='none',
                          alpha=.85, boxstyle='round,pad=0.18'))

def lane_label(y, number, text, color):
    ax.text(.3, y, f'{number}  {text}', ha='left', va='center',
            fontsize=7.5, color=color, family='monospace',
            bbox=dict(facecolor=BG, edgecolor=color,
                      linewidth=.9, boxstyle='round,pad=0.3', alpha=.8))

# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(8, 7.58, 'Stock Sentiment & Forecast Pipeline',
        ha='center', fontsize=14.5, fontweight='bold',
        color=PRI, family='monospace')
ax.text(8, 7.18,
        'Lambda  ·  S3 Medallion  ·  Bedrock Claude Haiku  ·  Glue / Athena  ·  Streamlit  ·  Terraform (IaC)',
        ha='center', fontsize=8.5, color=SEC, family='monospace')

# ── Lane labels ───────────────────────────────────────────────────────────────
lane_label(5.85, '[1]', 'INGEST   every 30 min, Mon-Fri market hours', C['event'])
lane_label(3.90, '[2]', 'ENRICH   triggered by S3:ObjectCreated on bronze/', C['bedrock'])
lane_label(1.95, '[3]', 'FORECAST daily 21:00 UTC, writes to silver/ + gold/', C['lambda'])

# ── Horizontal dividers ───────────────────────────────────────────────────────
for yy in [5.1, 3.1]:
    ax.axhline(yy, xmin=.01, xmax=.99, color=BORDER, lw=.8, ls='--', zorder=1)

# ── ROW 1 — Ingest ────────────────────────────────────────────────────────────
W, H = 2.05, .8
draw_box(1.5,  5.5, 1.85, H, 'EventBridge',    '30 min cron',           C['event'])
draw_box(4.2,  5.5, 2.2,  H, 'Ingest Lambda',  'Finnhub /company-news', C['lambda'])
draw_box(7.0,  5.5, 2.1,  H, 'S3  Bronze',     'raw JSON per ticker',   C['s3'])

draw_arrow(2.43, 5.5, 3.1, 5.5)
draw_arrow(5.3,  5.5, 5.95, 5.5)

# ── ROW 2 — Enrich ────────────────────────────────────────────────────────────
draw_arrow(7.0, 5.1, 7.0, 4.45, 'S3:ObjectCreated')

draw_box(7.0,  4.05, 2.2,  H, 'Enrich Lambda',  'Python 3.12 · moto-tested', C['lambda'])
draw_box(9.8,  4.05, 2.1,  H, 'Bedrock',        'Claude Haiku · −1→+1',      C['bedrock'])

draw_arrow(8.1, 4.05, 8.75, 4.05)
draw_arrow(7.0, 3.65, 7.0, 3.1, '')

# ── ROW 3 — Silver + Catalog ──────────────────────────────────────────────────
draw_box(7.0,  2.6,  2.1,  H, 'S3  Silver',     'Parquet · sentiment + prices', C['s3'])
draw_box(9.8,  2.6,  2.2,  H, 'Glue + Athena',  'daily crawler · schema-on-read', C['catalog'])

draw_arrow(8.05, 2.6, 8.7, 2.6)

# ── ROW 4 — Forecast ──────────────────────────────────────────────────────────
draw_box(1.5,  1.6,  1.85, H, 'EventBridge',     'daily 21:00 UTC',          C['event'])
draw_box(4.2,  1.6,  2.2,  H, 'Forecast Lambda', 'Alpha Vantage · 60-day bars', C['lambda'])
draw_box(7.0,  1.6,  2.1,  H, 'S3  Gold',        'forecasts + briefs JSON',  C['s3'])

draw_arrow(2.43, 1.6, 3.1, 1.6)
draw_arrow(5.3,  1.6, 5.95, 1.6)

# Forecast reads Athena for sentiment
draw_arrow(5.3, 1.95, 9.45, 2.2, 'reads sentiment', rad=-.28)

# ── DASHBOARD ─────────────────────────────────────────────────────────────────
draw_box(13.3, 2.2, 2.6, 2.0, 'Streamlit\nDashboard',
         '· Live Prices (60-day)\n· Sentiment Heatmap\n· AI Forecast & Brief', C['dash'])

# Athena → Dashboard
draw_arrow(10.9, 2.6, 12.0, 2.45)
# Gold → Dashboard
draw_arrow(8.05, 1.6, 12.0, 1.9, '', rad=-.18)

# ── Legend ─────────────────────────────────────────────────────────────────────
legend = [
    (C['event'],   'EventBridge'),
    (C['lambda'],  'Lambda'),
    (C['s3'],      'S3'),
    (C['bedrock'], 'Bedrock / AI'),
    (C['catalog'], 'Glue + Athena'),
    (C['dash'],    'Streamlit'),
]
lx, ly = .4, .72
for i, (clr, lbl) in enumerate(legend):
    xx = lx + i * 2.48
    ax.add_patch(plt.Circle((xx, ly), .09, color=clr, zorder=5))
    ax.text(xx + .2, ly, lbl, va='center', fontsize=7.5,
            color=SEC, family='monospace', zorder=5)

# ── Save ─────────────────────────────────────────────────────────────────────
import os
out = os.path.join(os.path.dirname(__file__), 'architecture.png')
plt.savefig(out, dpi=160, bbox_inches='tight',
            facecolor=BG, edgecolor='none', pad_inches=0.12)
print(f'Saved {out}')
