"""Paper 3 corrected batch20 figures: saved observations and saved intervals only.

Usage: python generate_paper3_figures.py --output NEW_DIRECTORY [--final]
Default input bundle is alongside this script. --repo ROOT additionally verifies
every selected input against its original corrective statistics path. This code
does not import model code, resample, fit, interpolate or run an experiment.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import warnings
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path.home() / '.cache' / 'paper3_figure_matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.text import Text
from PIL import Image

BLUE = '#6F8FAF'
ORANGE = '#C99A5A'
INK = '#222222'
FONTSIZE = 8.0
PDF_METADATA = {'Title': 'Paper 3: verified corrective batch20 experiment',
                'Author': 'Paper 3 research archive', 'Creator': 'Matplotlib',
                'CreationDate': None, 'ModDate': None}
PINS = {
 'PACKAGE_MANIFEST.json': '5a30e5519ed3fde36e78e7e31e6918849fb5fd2814f635aac0a8e80fa2624fde',
 'DELIVERY_MANIFEST.json': '2189bc4d91689717c4c87cec0e1f539f32aac7069673dff61bd626b939e7985f',
 'FINAL_INTEGRITY_CERTIFICATE.json': '86b9c104aacf708f7f060d1f99faa0215b7b3490327c6325c4ddf49353743398',
 'statistics_manifest.json': 'a2cd080532db281ca60ae89ee9edf5e272552689f8be9220eaf7c7857b3f1468',
 'statistics_execution_receipt.json': '82585cf06c15e2bebc2d37bea90ccb9b6f24aa78745c00f6fd3378a0a0742dec',
}
NAMES = ['final_paired_contrasts.csv', 'final_metrics_by_center.csv',
         'final_metrics_by_method.csv', 'final_metrics_by_trajectory.csv',
         'final_execution_cost_by_method.csv', 'final_execution_cost_by_trajectory.csv']

def sha(data):
    return hashlib.sha256(data).hexdigest()

def close(a, b):
    assert math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-14), (a, b)

def number(row, name):
    value = float(row[name])
    assert math.isfinite(value), (name, value)
    return value

def scientific(value):
    mantissa, exponent = f'{value:.2e}'.split('e')
    return mantissa.replace('-', '−') + ' × 10$^{' + str(int(exponent)) + '}$'

def load_data(folder, repo):
    meta = {}
    used = {}
    for name, pin in PINS.items():
        data = (folder / name).read_bytes()
        assert sha(data) == pin, ('AUTHORITY_HASH_CONFLICT', name)
        meta[name] = json.loads(data)
        used[name] = pin
    package = meta['PACKAGE_MANIFEST.json']['files_sha256']
    delivery = meta['DELIVERY_MANIFEST.json']
    certificate = meta['FINAL_INTEGRITY_CERTIFICATE.json']
    sm = meta['statistics_manifest.json']
    receipt = meta['statistics_execution_receipt.json']
    assert delivery['status'] == 'COMPLETED' and certificate['status'] == 'PASS'
    assert receipt['status'] == 'COMPLETED' and receipt['exit_code'] == 0
    assert receipt['statistics_manifest_sha256'] == PINS['statistics_manifest.json']
    assert package['DELIVERY_MANIFEST.json'] == PINS['DELIVERY_MANIFEST.json']
    assert package['FINAL_INTEGRITY_CERTIFICATE.json'] == PINS['FINAL_INTEGRITY_CERTIFICATE.json']
    assert package['manifests/statistics_manifest.json'] == PINS['statistics_manifest.json']
    assert package['manifests/statistics_execution_receipt.json'] == PINS['statistics_execution_receipt.json']
    tables = {}
    for name in NAMES:
        data = (folder / name).read_bytes()
        h = sha(data)
        assert h == sm['outputs_sha256'][name] == receipt['outputs_sha256'][name]
        assert h == package['statistics/' + name] == delivery['statistics_outputs_sha256']['statistics/' + name]
        if repo:
            original = repo / 'results/p7_7_integrity_replication_batch20_env_v3/statistics_batch20_env_v3' / name
            assert sha(original.read_bytes()) == h, ('CORRECTED_ORIGINAL_HASH_CONFLICT', name)
        tables[name] = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
        used[name] = h
    methods = {r['method']: r for r in tables['final_metrics_by_method.csv']}
    center_rows = tables['final_metrics_by_center.csv']
    assert len(center_rows) == 100 and len({(r['method'], r['center_id']) for r in center_rows}) == 100
    centers = sorted({int(r['center_id']) for r in center_rows})
    assert centers == list(range(33000, 33020))
    center = {(r['method'], int(r['center_id'])): number(r, 'lifecycle_service_loss') for r in center_rows}
    contrasts = tables['final_paired_contrasts.csv']
    assert [r['comparison'] for r in contrasts] == ['P7.7 - ' + n for n in ['B0', 'B1', 'B2', 'B8']]
    for r in contrasts:
        assert int(r['n_centers']) == 20 and int(r['bootstrap_resamples']) == 4000 and int(r['bootstrap_seed']) == 2904
        assert r['point_estimate_source'] == 'OBSERVED_METHOD_CENTER_MEAN_SUBTRACTION'
        baseline = r['comparison'].split(' - ')[1]
        observed = math.fsum(center['P7.7', c] for c in centers) / 20 - math.fsum(center[baseline, c] for c in centers) / 20
        close(observed, r['mean_difference'])
        close(number(methods['P7.7'], 'mean_lifecycle_service_loss') - number(methods[baseline], 'mean_lifecycle_service_loss'), observed)
        assert number(r, 'ci_low') <= number(r, 'mean_difference') <= number(r, 'ci_high')
    assert number(contrasts[-1], 'ci_low') < 0 < number(contrasts[-1], 'ci_high')
    trajectories = tables['final_metrics_by_trajectory.csv']
    assert len(trajectories) == 1200
    assert len({(r['method'], r['center_id'], r['seed'], r['scenario']) for r in trajectories}) == 1200
    costs = {r['method']: r for r in tables['final_execution_cost_by_method.csv']}
    cost_trajectories = tables['final_execution_cost_by_trajectory.csv']
    behavior = {}
    for m in ['B8', 'P7.7']:
        rows = [r for r in trajectories if r['method'] == m]
        assert len(rows) == 240 and all(int(r['stages']) == 24 for r in rows)
        stages = sum(int(r['stages']) for r in rows)
        opens = sum(int(r['gate_open_count']) for r in rows)
        ris = sum(int(r['ri_count']) for r in rows)
        close(opens / stages, methods[m]['gate_open_rate'])
        close(ris / stages, methods[m]['ri_rate'])
        work = number(costs[m], 'ri_search_updates_charged_total_recorded')
        candidates = number(costs[m], 'feasible_candidate_count_total_recorded')
        close(work, candidates * 50)
        tr_cost = [r for r in cost_trajectories if r['method'] == m]
        assert len(tr_cost) == 240
        close(sum(number(r, 'ri_search_updates_charged_stage_sum') for r in tr_cost), work)
        behavior[m] = {'stages': stages, 'admission_count': opens, 'admission_percent': 100 * opens / stages,
                       'candidate_updates': int(work), 'candidates': int(candidates), 'committed_ri': ris}
    # Prespecified expected values are assertions only, never the plotted data source.
    assert behavior['B8']['candidate_updates'] == 2664000 and behavior['P7.7']['candidate_updates'] == 871400
    assert behavior['B8']['committed_ri'] == 105 and behavior['P7.7']['committed_ri'] == 104
    assert behavior['B8']['admission_count'] == 5760 and behavior['P7.7']['admission_count'] == 1918
    paired = [{'center_id': c, 'Proposed': center['P7.7', c], 'B8': center['B8', c],
               'difference': center['P7.7', c] - center['B8', c]} for c in centers]
    close(math.fsum(r['difference'] for r in paired) / 20, contrasts[-1]['mean_difference'])
    return {'input_sha256': used, 'contrasts': contrasts, 'paired_centers': paired, 'behavior': behavior,
            'n_centers': 20, 'bootstrap_resamples': 4000, 'bootstrap_seed': 2904,
            'bootstrap_recomputed': False, 'unseen_heldout_claimed': False, 'original_mixed_data_used': False}

def style():
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': FONTSIZE,
        'axes.labelsize': 8, 'axes.titlesize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
        'legend.fontsize': 8, 'axes.linewidth': .7, 'lines.linewidth': 1,
        'text.color': INK, 'axes.labelcolor': INK, 'axes.edgecolor': INK,
        'xtick.color': INK, 'ytick.color': INK, 'figure.facecolor': 'white', 'axes.facecolor': 'white',
        'savefig.facecolor': 'white', 'pdf.fonttype': 42, 'ps.fonttype': 42,
        'axes.unicode_minus': True, 'mathtext.fontset': 'dejavusans', 'hatch.linewidth': .5})

def clean(ax):
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(length=3, width=.7)
    ax.grid(False)

def fig2(data):
    fig = plt.figure(figsize=(7.16, 4.5), dpi=160)
    a = fig.add_axes([.105, .555, .365, .325])
    zoom = fig.add_axes([.105, .23, .365, .13])
    b = fig.add_axes([.66, .14, .31, .74])
    for ax in [a, zoom, b]:
        clean(ax)
        ax.axvline(0, color='#555555', lw=.75, linestyle=(0, (3, 2)), zorder=0)
    fig.text(.025, .954, '(a)', weight='bold', fontsize=10, va='top')
    fig.text(.105, .954, 'Paired service-loss contrasts', fontsize=9, va='top')
    fig.text(.56, .954, '(b)', weight='bold', fontsize=10, va='top')
    fig.text(.66, .954, '20 paired centers', fontsize=9, va='top')
    for i, r in enumerate(data['contrasts']):
        mean, lo, hi = [number(r, n) / 1e-3 for n in ['mean_difference', 'ci_low', 'ci_high']]
        color = ORANGE if i == 3 else BLUE
        marker = 's' if i == 3 else 'o'
        a.errorbar(mean, i, xerr=[[mean-lo], [hi-mean]], fmt=marker,
                   markersize=4.6, color=color, ecolor=color, elinewidth=1.3, capsize=3, zorder=3)
    a.set_yticks(range(4), ['B0', 'B1', 'B2', 'B8'])
    a.set_ylim(3.5, -.5)
    a.set_xlim(-5, .5)
    a.set_xticks([-4, -2, 0])
    a.set_xlabel('Proposed − baseline (×10$^{-3}$)', labelpad=5)
    fig.text(.105, .432, 'B8 detail: linear zoom of the same interval', fontsize=8)
    r = data['contrasts'][-1]
    mean, lo, hi = [number(r, n) / 1e-5 for n in ['mean_difference', 'ci_low', 'ci_high']]
    zoom.errorbar(mean, 0, xerr=[[mean-lo], [hi-mean]], fmt='s', markersize=4.6,
                  color=ORANGE, elinewidth=1.3, capsize=3)
    zoom.set(xlim=(-1, 10), ylim=(-.7, .7), yticks=[], xticks=[0, 2, 4, 6, 8, 10])
    zoom.set_xlabel('Proposed − B8 (×10$^{-5}$)', labelpad=4)
    zoom.spines['left'].set_visible(False)
    fig.text(.105, .375, '95% CI crosses zero', fontsize=8)
    fig.text(.105, .097, 'CI: [' + scientific(number(r, 'ci_low')) + ', ' + scientific(number(r, 'ci_high')) + ']', fontsize=8)
    x = [r['difference'] / 1e-4 for r in data['paired_centers']]
    b.scatter(x, list(range(20)), s=19, marker='s', color=ORANGE, edgecolors=INK, linewidths=.3, zorder=3)
    b.set_yticks(range(20), [str(r['center_id']) for r in data['paired_centers']])
    b.set(xlim=(-.5, 6.5), ylim=(19.7, -.7), xticks=[0, 2, 4, 6])
    b.set_xlabel('Proposed − B8 (×10$^{-4}$)', labelpad=5)
    b.set_ylabel('Center ID', labelpad=5)
    zero_count = sum(r['difference'] == 0 for r in data['paired_centers'])
    b.text(.94, .68, str(zero_count) + ' exact zero\ndifferences', transform=b.transAxes, ha='right', va='top', fontsize=8)
    # Label the smallest-magnitude nonzero point because it visually approaches
    # the zero line. Every point remains displayed in center-ID order.
    smallest = min((i for i,r in enumerate(data['paired_centers']) if r['difference'] != 0),
                   key=lambda i: abs(data['paired_centers'][i]['difference']))
    b.annotate(scientific(data['paired_centers'][smallest]['difference']), xy=(x[smallest], smallest), xytext=(.65, smallest), textcoords='data',
               fontsize=8, va='center')
    fig.text(.105, .015, 'Mean lifecycle service-loss differences; negative values favor Proposed.', fontsize=8)
    return fig

def fig3(data):
    fig = plt.figure(figsize=(7.16, 2.8), dpi=160)
    panels = [(.095, 'Search admission', 'Stage decisions (%)', 'admission_percent', 1, 118, [0,25,50,75,100]),
              (.42, 'Candidate-search\noptimizer updates', 'Updates (millions)', 'candidate_updates', 1e6, 3.15, [0,1,2,3]),
              (.745, 'Committed RI', 'RI actions (count)', 'committed_ri', 1, 125, [0,30,60,90,120])]
    for i, (left, title, ylabel, key, scale, upper, ticks) in enumerate(panels):
        ax = fig.add_axes([left, .20, .225, .57])
        clean(ax)
        values = [data['behavior'][m][key] / scale for m in ['B8','P7.7']]
        bars = ax.bar([0, 1], values, width=.56, color=[BLUE, ORANGE], edgecolor=INK, linewidth=.65)
        bars[1].set_hatch('///')
        for j, v in enumerate(values):
            raw = data['behavior'][['B8','P7.7'][j]][key]
            label = (f'{raw:.2f}%' if raw != 100 else '100%') if key == 'admission_percent' else f'{raw:,}'
            ax.text(j, v + upper*.034, label, ha='center', va='bottom', fontsize=8)
        ax.set(xlim=(-.62,1.62), ylim=(0,upper), yticks=ticks)
        ax.set_xticks([0,1], ['B8','Proposed'])
        ax.set_ylabel(ylabel, labelpad=5)
        fig.text(left-.055, .965, '('+'abc'[i]+')', weight='bold', fontsize=10, va='top')
        fig.text(left+.035, .965, title, fontsize=9, va='top', ha='left')
    fig.text(.095, .035, '5,760 stage decisions per method; candidate-search updates are not end-to-end cost.', fontsize=8)
    return fig

def audit_layout(fig):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    visible = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text()]
    clipped = []
    for t in visible:
        box = t.get_window_extent(renderer)
        if box.x0 < -1 or box.y0 < -1 or box.x1 > canvas.x1+1 or box.y1 > canvas.y1+1:
            clipped.append(t.get_text())
    tick_collisions = []
    for ax in fig.axes:
        for labels in [ax.get_xticklabels(), ax.get_yticklabels()]:
            boxes = [(t.get_text(), t.get_window_extent(renderer)) for t in labels if t.get_visible() and t.get_text()]
            for (ta, ba), (tb, bb) in zip(boxes, boxes[1:]):
                if ba.overlaps(bb):
                    tick_collisions.append([ta, tb])
    minimum = min(t.get_fontsize() for t in visible)
    assert not clipped and not tick_collisions and minimum >= 8, (clipped, tick_collisions, minimum)
    return {'status':'PASS', 'minimum_text_pt': minimum, 'text_clipping':clipped,
            'adjacent_tick_collisions':tick_collisions, 'figure_inches':list(fig.get_size_inches()),
            'manual_visual_review_required':True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-bundle', type=Path, default=Path(__file__).resolve().parent/'inputs')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--final', action='store_true', help='Export vector PDFs and 600-dpi PNGs after preview approval')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = load_data(args.input_bundle, args.repo)
    style()
    checks = {}
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter('always')
        for name, creator in [('Fig2_Paired_Service_Loss',fig2), ('Fig3_Selective_Search',fig3)]:
            fig = creator(data)
            checks[name] = audit_layout(fig)
            target = args.output / name
            if args.final:
                fig.savefig(str(target)+'.pdf', metadata=PDF_METADATA)
                fig.savefig(str(target)+'.png', dpi=600, metadata={'Software':'Matplotlib; corrected batch20 saved data'})
            else:
                fig.savefig(str(target)+'_preview.png', dpi=180)
                Image.open(str(target)+'_preview.png').convert('L').save(str(target)+'_grayscale.png')
            plt.close(fig)
        glyph = [str(w.message) for w in seen if 'Glyph' in str(w.message) and 'missing' in str(w.message)]
        assert not glyph, glyph
    checks['missing_glyph_warnings'] = glyph
    checks['runtime'] = {'matplotlib':matplotlib.__version__, 'font':'DejaVu Sans', 'font_minimum_pt':8,
                         'png_dpi':600 if args.final else 180, 'pdf_fonttype':42, 'AI_or_seaborn_used':False}
    (args.output/'PLOT_DATA.json').write_text(json.dumps(data,indent=2,sort_keys=True),encoding='utf-8')
    (args.output/'LAYOUT_CHECK.json').write_text(json.dumps(checks,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({'status':'PASS','phase':'final' if args.final else 'preview','figures':list(checks)[:2]}))

if __name__ == '__main__':
    main()
