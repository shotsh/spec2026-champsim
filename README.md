# SPEC2026 log analysis

Read completed single-core ChampSim logs and the trace package's existing weights to calculate IPC, CPI, weighted cycles and speedup. Requires Python 3.6+.

## Quick start

Set `SPEC2026_TRACE_DIR` to the top-level trace directory containing the supplied `trace-index.tsv`.

```sh
git clone https://github.com/shotsh/spec2026-champsim.git
cd spec2026-champsim
SPEC2026_TRACE_DIR="/path/to/spec2026-traces"
python3 summarize.py example/baseline example/variant \
    --weights "$SPEC2026_TRACE_DIR/trace-index.tsv" \
    --benchmark 721.gcc_r --out example/summary/gcc
```

This reads full, unmodified GCC output logs with their original filenames and the original supplied weights. The command prints about **1.00309x speedup** and writes:

- `example/summary/gcc/inputs.csv`: weighted cycles, IPC and CPI for each input.
- `example/summary/gcc/benchmarks.csv`: benchmark speedup and cycle ratio, about **0.99692** in this example.

The example also includes `727.cppcheck_r`. Change `--benchmark` to that name and `--out` to `example/summary/cppcheck` to try it. Both examples contain all three inputs and use the original package index directly.

## Analyze your logs

Keep the `trace-index.tsv` supplied with your traces. Put the original configuration's output logs in `logs/original` and the modified configuration's logs in `logs/modified`. Keep their contents and filenames unchanged. Subdirectories are allowed.

Each log is matched to its weights using the trace path printed in `CPU 0 runs ...`. Include every indexed trace of the selected benchmark in both directories. Logs must contain their printed warmup/measurement settings and single-core completion counters.

```sh
SPEC2026_TRACE_DIR="/path/to/spec2026-traces"
python3 summarize.py logs/original logs/modified \
    --weights "$SPEC2026_TRACE_DIR/trace-index.tsv" \
    --benchmark 721.gcc_r --out analysis/gcc
```

| Input | Meaning |
| --- | --- |
| First directory | Logs from the original configuration. |
| Second directory | Logs from the modified configuration. |
| `--weights` | The trace package's index with its existing weights. Change the example path to your file. |
| `--benchmark` | One benchmark name from that index. |
| `--out` | Report directory. Default: `summary/<benchmark>`. |

## ChampSim log format

Pass the full output log unchanged. The reader uses these lines (excerpt, with the trace path abbreviated):

```text
Warmup Instructions: 200000000
Simulation Instructions: 500000000
Number of CPUs: 1
Simulation complete CPU 0 instructions: 500000000 cycles: 964424425 ...
ChampSim completed all CPUs
CPU 0 runs <trace path>
```

The lines can appear anywhere in the log. Progress messages and cache/DRAM statistics can stay. All selected logs must have the same warmup and measurement settings. CPI/IPC use the printed requested instruction count, including normal completion overshoot. Missing, incomplete, duplicate or inconsistent results stop calculation.

## CSV output

`inputs.csv` has one row per input. `benchmarks.csv` combines inputs geometrically. `baseline_*` refers to the first log directory and `variant_*` to the second.

| Columns | Meaning |
| --- | --- |
| `benchmark`, `input` | Workload identity. `input` appears in `inputs.csv`. |
| `n_slices_used`, `n_slices_in_weights` | SimPoints used and listed in the index. |
| `weight_coverage` | Weight coverage, `1` for complete results. |
| `n_inputs_used`, `n_inputs_in_weights` | Inputs used and expected, in `benchmarks.csv`. |
| `weighted_baseline`, `weighted_variant` | Weighted cycles for the original and modified configurations. |
| `baseline_cpi`, `variant_cpi` | Cycles per instruction, in `inputs.csv`. |
| `baseline_ipc`, `variant_ipc` | Instructions per cycle, in `inputs.csv`. |
| `weighted_ratio` | Speedup: original cycles / modified cycles. Larger is faster. |
| `weighted_change_pct` | Performance change: `100 * (speedup - 1)`, in percent. |
| `cycle_ratio` | Modified cycles / original cycles. Smaller is faster. |

Cycle ratios represent time ratios at equal clock frequencies. For multiple benchmarks, repeat the command from your shell.
