#!/usr/bin/env python3
"""Compare one benchmark using supplied weights and completed ChampSim logs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import math
from pathlib import Path
import re
import sys

from weighted import ManifestError, _side_ratio, simpoint_weighted_input_tables


FIELDS = ['benchmark', 'input_number', 'workload_id', 'simpoint_index', 'weight', 'trace_path']


def identity(row):
    return row['benchmark'], row['input_number'], row['simpoint_index']


def read_index(path):
    with path.open(newline='') as source:
        reader = csv.DictReader(source, delimiter='\t')
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError('{}: missing trace index columns'.format(path))
        rows = list(reader)
    seen, weights = set(), {}
    for row in rows:
        key = identity(row)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', key[0]):
            raise ValueError('Invalid benchmark: {}'.format(key[0]))
        if not key[1].isdigit() or not key[2].isdigit() or key in seen:
            raise ValueError('Invalid or duplicate identity: {}'.format(key))
        seen.add(key)
        weight = float(row['weight'])
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError('Invalid weight for {}'.format(key))
        weights.setdefault(key[:2], []).append(weight)
        trace = Path(row['trace_path'])
        if trace.is_absolute() or '..' in trace.parts:
            raise ValueError('Trace path must be relative to the package: {}'.format(trace))
    if not rows:
        raise ValueError('No traces selected')
    for key, values in weights.items():
        if abs(math.fsum(values) - 1) > .001:
            raise ValueError('Weights do not sum to one for {}'.format(key))
    return rows

CYCLES = re.compile('cycles: (?P<sim_cycles>[0-9]+)')
INSTRUCTIONS = re.compile('instructions: (?P<sim_instructions>[0-9]+)')


def header_number(text, label, path):
    values = re.findall(r'^' + re.escape(label) + r': ([0-9]+)[ \t]*$', text, re.MULTILINE)
    if len(values) != 1:
        raise ValueError('Missing or duplicate {}: {}'.format(label, path))
    return int(values[0])


def read_log(path, aliases):
    text = path.read_text()
    traces = re.findall(r'^CPU 0 runs (.+)$', text, re.MULTILINE)
    selected = [aliases.get(str(Path(*Path(trace).parts[-3:]))) or aliases.get(Path(trace).name)
                for trace in traces]
    selected = [key for key in selected if key is not None]
    if not selected:
        return None
    if len(traces) != 1:
        raise ValueError('Expected one CPU0 trace header: {}'.format(path))
    warmup = header_number(text, 'Warmup Instructions', path)
    requested = header_number(text, 'Simulation Instructions', path)
    cpus = header_number(text, 'Number of CPUs', path)
    completed = re.findall(r'^Simulation complete CPU (\d+) (.*)$', text, re.MULTILINE)
    if cpus != 1 or len(completed) != 1 or completed[0][0] != '0':
        raise ValueError('Expected one CPU0 completion: {}'.format(path))
    if 'ChampSim completed all CPUs' not in text or 'DEADLOCK!' in text:
        raise ValueError('Incomplete or failed simulation: {}'.format(path))
    cycles, instructions = CYCLES.search(completed[0][1]), INSTRUCTIONS.search(completed[0][1])
    if cycles is None or instructions is None:
        raise ValueError('Missing completion counters: {}'.format(path))
    cycles, instructions = int(cycles.group('sim_cycles')), int(instructions.group('sim_instructions'))
    if requested <= 0 or instructions < requested or cycles <= 0:
        raise ValueError('Incomplete measurement: {}'.format(path))
    return selected[0], (warmup, requested), cycles


def read_results(directories, rows):
    aliases = {}
    for row in rows:
        flat = '{}_i{}_{}B.champsimtrace.xz'.format(
            row['benchmark'].replace('.', '_'), row['input_number'], row['simpoint_index'])
        for name in (str(Path(row['trace_path'])), flat):
            if name in aliases and aliases[name] != identity(row):
                raise ValueError('Ambiguous trace identity: {}'.format(name))
            aliases[name] = identity(row)
    paths = []
    for side, directory in enumerate(directories):
        if not directory.is_dir():
            raise ValueError('Not a log directory: {}'.format(directory))
        paths.extend((side, path) for path in directory.rglob('*') if path.is_file())
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(paths)))) as pool:
        records = list(pool.map(lambda item: read_log(item[1], aliases), paths))
    sides = [{}, {}]
    for (side, path), record in zip(paths, records):
        if record is None:
            continue
        key, window, cycles = record
        if key in sides[side]:
            raise ValueError('Duplicate log for {}: {}'.format(key, path))
        sides[side][key] = (window, cycles)
    for directory, results in zip(directories, sides):
        missing = [identity(row) for row in rows if identity(row) not in results]
        if missing:
            raise ValueError('Missing logs in {} for {}. Check CPU 0 runs trace paths.'.format(directory, missing))
    windows = {window for results in sides for window, _ in results.values()}
    if len(windows) != 1:
        raise ValueError('Baseline and variant measurement windows differ across selected logs')
    instructions = next(iter(windows))[1]
    values = {identity(row): (sides[0][identity(row)][1], sides[1][identity(row)][1]) for row in rows}
    return values, instructions


def write_csv(directory, name, rows):
    with (directory / name).open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('variant', type=Path)
    parser.add_argument('--weights', required=True, type=Path, help='supplied trace-index.tsv')
    parser.add_argument('--benchmark', required=True)
    parser.add_argument('--out', type=Path, help='report directory, default: summary/<benchmark>')
    args = parser.parse_args()
    rows = [row for row in read_index(args.weights) if row['benchmark'] == args.benchmark]
    if not rows:
        raise ValueError('No traces for benchmark: {}'.format(args.benchmark))
    values, instructions = read_results((args.baseline, args.variant), rows)
    slices = {identity(row): (row['benchmark'], row['input_number'], float(row['weight'])) for row in rows}
    benchmarks, inputs = simpoint_weighted_input_tables(values, slices, 'baseline')
    for row in inputs:
        row.update(baseline_cpi=row['weighted_baseline'] / instructions,
                   variant_cpi=row['weighted_variant'] / instructions,
                   baseline_ipc=instructions / row['weighted_baseline'],
                   variant_ipc=instructions / row['weighted_variant'])
    for row in inputs + benchmarks:
        row['cycle_ratio'] = _side_ratio(row['weighted_baseline'], row['weighted_variant'], 'variant')
    output = args.out if args.out is not None else Path('summary') / args.benchmark
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output, 'inputs.csv', inputs)
    write_csv(output, 'benchmarks.csv', benchmarks)
    print('{}: {:.12g}x speedup. Wrote {}'.format(args.benchmark, benchmarks[0]['weighted_ratio'], output))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, ManifestError) as error:
        sys.exit(str(error))
