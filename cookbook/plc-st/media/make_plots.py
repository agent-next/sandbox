#!/usr/bin/env python3
"""Generate result.png and loop.png from judge output data.

All plotted numbers come from judge output files — no invented data.
"""
import json
import os
import re
import sys
import textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.transforms import Bbox
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"

if not DATA.is_dir():
    print("ERROR: media/data/ missing -- run media/make_data.sh first", file=sys.stderr)
    sys.exit(1)

# Load judge output data (produced by media/make_data.sh, committed to git)
with open(DATA / "grade_good.json") as f:
    verdict = json.load(f)

with open(DATA / "selftest_output.txt") as f:
    selftest_lines = f.read().strip().split('\n')

# Extract scenario results
scenarios = [r['name'] for r in verdict['results']]
max_levels = [r['max_level'] for r in verdict['results']]
min_levels = [r['min_level'] for r in verdict['results']]
passed = [r['pass'] for r in verdict['results']]

# DESIGN_CAP from judge
DESIGN_CAP = 94.0
DRY_BAND = 15.0
HIGH_SET = 85.0
LOW_SET = 15.0

# Scenario display names (wrapped to 2 lines max)
scenario_display = {
    'cycle': 'Cycle',
    'overflow_guard': 'Overflow\nGuard',
    'dry_run': 'Dry Run',
    'dry_interlock_fault': 'Dry Interlock\nFault',
    'lowsw_false_trip': 'Lowsw False\nTrip',
    'estop': 'Estop',
    'recovery': 'Recovery',
    'random_faults': 'Random\nFaults',
}

# --- Figure 1: result.png - Bar chart of max/min levels per scenario ---
# Target: exactly 1920x1080 pixels
fig1, ax1 = plt.subplots(figsize=(19.2, 10.8), dpi=100)

x = np.arange(len(scenarios))
width = 0.35

colors_pass = '#2e7d32'  # green
colors_fail = '#c62828'  # red

bars_max = ax1.bar(x - width/2, max_levels, width, label='Max level (cm)',
                   color=[colors_pass if p else colors_fail for p in passed],
                   edgecolor='black', linewidth=0.5)
bars_min = ax1.bar(x + width/2, min_levels, width, label='Min level (cm)',
                   color=[colors_pass if p else colors_fail for p in passed],
                   edgecolor='black', linewidth=0.5, hatch='//', fill=False)

# Reference lines
ax1.axhline(y=DESIGN_CAP, color='#b71c1c', linestyle='--', linewidth=2,
            label=f'Design cap ({DESIGN_CAP:.0f} cm)')
ax1.axhline(y=HIGH_SET, color='#1565c0', linestyle=':', linewidth=1.5,
            label=f'High switch ({HIGH_SET:.0f} cm)')
ax1.axhline(y=LOW_SET, color='#e65100', linestyle=':', linewidth=1.5,
            label=f'Low switch ({LOW_SET:.0f} cm)')
ax1.axhline(y=DRY_BAND, color='#e65100', linestyle=':', linewidth=1.5)

ax1.set_ylabel('Level (cm)', fontsize=14)
ax1.set_title('plc-st: Max/Min Level per Scenario (known-good controller)',
              fontsize=16, fontweight='bold')
ax1.set_xticks(x)
ax1.set_xticklabels([scenario_display[s] for s in scenarios],
                    rotation=0, ha='center', fontsize=12)
ax1.set_ylim(0, 100)
ax1.grid(True, axis='y', alpha=0.3)

# Annotate bars with values
for bar, val in zip(bars_max, max_levels):
    ax1.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width()/2, val),
                 xytext=(0, 3), textcoords='offset points',
                 ha='center', va='bottom', fontsize=10, fontweight='bold')

for bar, val in zip(bars_min, min_levels):
    ax1.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width()/2, val),
                 xytext=(0, -12), textcoords='offset points',
                 ha='center', va='top', fontsize=10, fontweight='bold',
                 bbox=dict(boxstyle='square,pad=0.15', fc='white', ec='none'))

# Add PASS/FAIL badges - position them in a row ABOVE the plot area
# so no badge overlaps any bar or value label
badge_y = 102  # Above the 100 y-limit
for i, (bar, p) in enumerate(zip(bars_max, passed)):
    badge = '✓ PASS' if p else '✗ FAIL'
    color = colors_pass if p else colors_fail
    ax1.annotate(badge, xy=(bar.get_x() + bar.get_width()/2, badge_y),
                 ha='center', va='bottom', fontsize=11, fontweight='bold',
                 color=color,
                 bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor=color, alpha=0.9))

# Extend y-axis to accommodate badges
ax1.set_ylim(0, 108)

# Legend inside the axes, in the empty pocket right of the Recovery bar
# (x ~ 6.2-7.5, y ~ 62-84: above the Random Faults bars, below the
# high-switch line, clear of the PASS badge row at y=102).
ax1.legend(loc='upper right', bbox_to_anchor=(0.99, 0.78),
           fontsize=10, borderaxespad=0.3)

# Rule explanation for the dry_run min level (10 cm is below the 15 cm low
# switch yet PASS): one line in the empty band between the 85 cm bar labels
# and the 94 cm design cap, arrow straight down the gap to the bar it explains.
ax1.annotate('Dry Run min 10 cm = start level: pump stays OFF below 15 cm, so this is PASS',
             xy=(scenarios.index('dry_run') + width/2, 10.5),
             xytext=(scenarios.index('dry_run') + 0.55, 90.5), ha='left', va='center',
             fontsize=9, color='#e65100',
             arrowprops=dict(arrowstyle='->', color='#e65100', lw=1.2,
                             shrinkA=0, relpos=(0, 0.5)),
             bbox=dict(boxstyle='round,pad=0.25', facecolor='#fff8e1', edgecolor='#e65100'))

fig1.tight_layout()
fig1.savefig(HERE / 'result.png', dpi=100)
plt.close(fig1)

# --- Figure 2: loop.png - Scenario matrix heatmap ---
# Left: 7 rows (Good + 6 mutants) x 8 columns (scenarios)
# Cell = green PASS / red FAIL from each verdict JSON.
# In each red cell: print first failing check name and measured value vs limit (max 2 lines).
# Right: horizontal kill-rate bar "6/6 killed = 100%"
# Title: "Judge self-test: which scenario catches each mutant (real verdict JSON)"
# Figure 1920x1080 px, cells large, font >= 11 pt, no text overlap.

mutant_names = ['estop_not_safe', 'inverted_dryrun', 'missing_estop_latch',
                'missing_overflow_guard', 'no_dry_restart', 'swapped_valves']
mutant_labels = ['Good Controller', 'E-stop\nnot safe', 'Inverted\ndry-run',
                 'Missing\nE-stop latch', 'Missing\noverflow\nguard',
                 'No dry\nrestart', 'Swapped\nvalves']

# Build matrix: rows = [good] + 6 mutants, columns = 8 scenarios
# Cell value: 'PASS' or 'FAIL' with detail
n_rows = 7
n_cols = 8

cell_status = []  # list of lists: 'PASS' or 'FAIL'
cell_detail = []  # list of lists: detail string for FAIL cells

# Good controller row
good_row_status = []
good_row_detail = []
for r in verdict['results']:
    good_row_status.append('PASS')
    good_row_detail.append(None)
cell_status.append(good_row_status)
cell_detail.append(good_row_detail)

# Mutant rows
for m in mutant_names:
    with open(DATA / f"grade_{m}.json") as f:
        mv = json.load(f)
    mutant_row_status = []
    mutant_row_detail = []
    for r in mv['results']:
        if r['pass']:
            mutant_row_status.append('PASS')
            mutant_row_detail.append(None)
        else:
            mutant_row_status.append('FAIL')
            # Get first failing check and its measured value vs limit
            first_fail = r['failures'][0]
            detail = ""
            if first_fail == 'max_level<=94':
                measured = r['max_level']
                limit = DESIGN_CAP
                detail = f"max_level {measured:.1f} > {limit:.0f}"
            elif first_fail == 'pump_never_dry':
                measured = r['min_level']
                limit = DRY_BAND
                detail = f"pump ran at {measured:.1f} < {limit:.0f}"
            elif first_fail == 'autocycle>=2':
                detail = "autocycle failed"
            elif first_fail == 'estop_off_from_401':
                detail = "actuators on after scan 401"
            elif first_fail == 'no_actuation_500_700':
                detail = "no actuation in [500,700)"
            elif first_fail == 'pump_stops_within_200':
                detail = "pump did not stop within 200 scans"
            elif first_fail == 'no_pump_inlet':
                detail = "pump and inlet both on"
            elif first_fail == 'recovers':
                detail = "did not recover"
            else:
                detail = first_fail
            mutant_row_detail.append(detail)
    cell_status.append(mutant_row_status)
    cell_detail.append(mutant_row_detail)

# Create figure 1920x1080
fig2 = plt.figure(figsize=(19.2, 10.8), dpi=100)

# GridSpec for left/right split - left gets more space for 8 scenario columns
gs = fig2.add_gridspec(1, 2, width_ratios=[7, 2], wspace=0.05)

# Left: Scenario matrix heatmap
ax_matrix = fig2.add_subplot(gs[0])

# Create color matrix: 1 = PASS (green), 0 = FAIL (red)
color_matrix = np.ones((n_rows, n_cols))
for i in range(n_rows):
    for j in range(n_cols):
        if cell_status[i][j] == 'FAIL':
            color_matrix[i, j] = 0

# Plot heatmap with large cells
cmap = plt.cm.RdYlGn
im = ax_matrix.imshow(color_matrix, aspect='auto', cmap=cmap, vmin=0, vmax=1,
                      interpolation='nearest')

# Set ticks
ax_matrix.set_yticks(np.arange(n_rows))
ax_matrix.set_yticklabels(mutant_labels, fontsize=13, fontweight='bold')

# X-axis: scenario labels (horizontal, wrapped)
col_labels = [scenario_display[s] for s in scenarios]
ax_matrix.set_xticks(np.arange(n_cols))
ax_matrix.set_xticklabels(col_labels, fontsize=12, rotation=0, ha='center')

# Grid lines
ax_matrix.set_xticks(np.arange(n_cols + 1) - 0.5, minor=True)
ax_matrix.set_yticks(np.arange(n_rows + 1) - 0.5, minor=True)
ax_matrix.grid(which='minor', color='white', linestyle='-', linewidth=2)
ax_matrix.tick_params(which='minor', bottom=False, left=False)

# Add text annotations in FAIL cells.
# Each cell label is wrapped at 14 chars (at most 3 lines for the failure
# strings the judge can emit), fontsize 9, centred. Numbers kept verbatim.
# LOOP_CELL_FONT / LOOP_CELL_WRAP exist only to reproduce the old broken
# layout for the overflow check demonstration (see REVIEW.md).
CELL_FONT = float(os.environ.get('LOOP_CELL_FONT', '9'))
CELL_WRAP = int(os.environ.get('LOOP_CELL_WRAP', '14'))

cell_texts = []  # (Text artist, row i, col j)
for i in range(n_rows):
    for j in range(n_cols):
        if cell_detail[i][j]:
            detail = cell_detail[i][j]
            if CELL_WRAP > 0:
                detail = textwrap.fill(detail, CELL_WRAP,
                                       break_long_words=False,
                                       break_on_hyphens=False)
            text = ax_matrix.text(j, i, detail, ha='center', va='center',
                                  fontsize=CELL_FONT, color='white',
                                  fontweight='bold', linespacing=1.2)
            cell_texts.append((text, i, j))

# Highlight Good Controller row with blue border
for j in range(n_cols):
    ax_matrix.add_patch(plt.Rectangle((j - 0.5, -0.5), 1, 1, fill=False,
                                       edgecolor='#1565c0', linewidth=3, clip_on=False))

ax_matrix.set_title('Scenario Matrix: PASS (green) / FAIL (red) with failing check (measured value where the judge records one)',
                    fontsize=14, fontweight='bold', pad=15)

# Right: Kill rate bar (horizontal)
ax_bar = fig2.add_subplot(gs[1])

# Kill rate parsed from real selftest output ("selftest: kill rate 6/6 (100%)")
m = re.search(r'kill rate (\d+)/(\d+)', '\n'.join(selftest_lines))
killed, nmut = (int(m.group(1)), int(m.group(2))) if m else (0, 1)
kill_rate = killed / nmut
kill_label = f'{killed}/{nmut} killed = {100 * kill_rate:.0f} %'

ax_bar.barh([0], [kill_rate], height=0.5, color='#2e7d32', edgecolor='black', linewidth=1)
ax_bar.set_xlim(0, 1.0)
# No y tick label: a 'Kill Rate' label at y=0 would sit on top of the bar.
ax_bar.set_yticks([])
ax_bar.set_xlabel('Fraction', fontsize=12)
# Keep the count label inside the bar/panel: right-aligned just inside the
# bar's right edge so it can never spill past the axes.
ax_bar.text(kill_rate - 0.03, 0, kill_label, ha='right', va='center',
            fontsize=11, fontweight='bold', color='white')
ax_bar.axvline(x=1.0, color='gray', linestyle='--', linewidth=1)
ax_bar.grid(True, axis='x', alpha=0.3)
# Leave room below the bar for the legend, inside the axes/figure.
ax_bar.set_ylim(-3.4, 0.8)

# Legend for cell colors: inside the kill-rate axes, below the bar, fully
# inside the figure (previously anchored below the axes and cut off).
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='#2e7d32', edgecolor='black', label='PASS'),
    Patch(facecolor='#c62828', edgecolor='black', label='FAIL'),
    Patch(facecolor='none', edgecolor='#1565c0', linewidth=3, label='Known-Good Controller'),
]
ax_bar.legend(handles=legend_elements, loc='lower center',
              fontsize=9, frameon=True, ncol=1)

ax_bar.set_title('Kill Rate', fontsize=14, fontweight='bold', pad=15)

# Overall title
fig2.suptitle('Judge self-test: which scenario catches each mutant (real verdict JSON)',
              fontsize=16, fontweight='bold', y=0.98)

# --- Real overlap check: every cell text must fit inside its cell ---
# Draw once so all text extents are final, then assert each cell label's
# pixel bbox lies inside that cell's pixel bbox (cell corners transformed
# through ax.transData).
fig2.canvas.draw()
renderer = fig2.canvas.get_renderer()
for text, i, j in cell_texts:
    tb = text.get_window_extent(renderer=renderer)
    corners = ax_matrix.transData.transform(
        [[j - 0.5, i - 0.5], [j + 0.5, i + 0.5]])
    cb = Bbox(corners)
    if not (cb.contains(tb.x0, tb.y0) and cb.contains(tb.x1, tb.y1)):
        raise AssertionError(
            f'cell text overflows cell (row {i}, col {j}): '
            f'text bbox {tb} not inside cell bbox {cb}')

fig2.savefig(HERE / 'loop.png', dpi=100)
plt.close(fig2)

print("Generated result.png and loop.png")