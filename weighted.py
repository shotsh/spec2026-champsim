"""Weighted comparisons of paired simulation cycles."""
import math


class ManifestError(Exception):
    pass


def _weighted_sides(names, weights, values):
    """The weight of the named paired slices and each side's mean weighted by the weights renormalized over them."""
    used = math.fsum(weights[n] for n in names)
    baseline = math.fsum(weights[n] * values[n][0] for n in names) / used
    variant = math.fsum(weights[n] * values[n][1] for n in names) / used
    return used, baseline, variant

def _side_ratio(baseline, variant, numerator):
    top, bottom = (baseline, variant) if numerator == "baseline" else (variant, baseline)
    return top / bottom if bottom > 0 and math.isfinite(top) and math.isfinite(bottom) else None

def _change(ratio):
    return None if ratio is None else 100.0 * (ratio - 1.0)

def _positive_geomean(values):
    return math.exp(math.fsum(math.log(v) for v in values) / len(values))

def simpoint_weighted_input_tables(values, slices, numerator):
    """Return input and benchmark comparisons from paired cycles and supplied weights."""
    for name in values:
        if name not in slices:
            raise ManifestError(f"simpoint_weighted: paired slice {name} has no weight in the weights table")
    weights = {name: weight for name, (_, _, weight) in slices.items()}
    listed, paired = {}, {}
    for name, (benchmark, input_name, _) in slices.items():
        listed.setdefault(benchmark, {}).setdefault(input_name, []).append(name)
        if name in values:
            paired.setdefault(benchmark, {}).setdefault(input_name, []).append(name)
    benchmark_rows, input_rows = [], []
    for benchmark in sorted(paired):
        sides, coverages = [], []
        for input_name in sorted(listed[benchmark]):
            in_table = listed[benchmark][input_name]
            names = sorted(paired[benchmark].get(input_name, []))
            row = {"benchmark": benchmark, "input": input_name, "n_slices_used": len(names), "n_slices_in_weights": len(in_table),
                   "weight_coverage": 0.0, "weighted_baseline": None, "weighted_variant": None, "weighted_ratio": None,
                   "weighted_change_pct": None}
            if names:
                used, baseline, variant = _weighted_sides(names, weights, values)
                ratio = _side_ratio(baseline, variant, numerator)
                row.update(weight_coverage=used / math.fsum(weights[n] for n in in_table), weighted_baseline=baseline,
                           weighted_variant=variant, weighted_ratio=ratio, weighted_change_pct=_change(ratio))
                sides.append((baseline, variant))
            coverages.append(row["weight_coverage"])
            input_rows.append(row)
        defined = all(math.isfinite(side) and side > 0 for pair in sides for side in pair)
        baseline = _positive_geomean([b for b, _ in sides]) if defined else None
        variant = _positive_geomean([v for _, v in sides]) if defined else None
        ratio = _side_ratio(baseline, variant, numerator) if defined else None
        benchmark_rows.append({"benchmark": benchmark, "n_slices_used": sum(len(v) for v in paired[benchmark].values()),
                               "n_slices_in_weights": sum(len(v) for v in listed[benchmark].values()),
                               "weight_coverage": min(coverages), "weighted_baseline": baseline, "weighted_variant": variant,
                               "weighted_ratio": ratio, "weighted_change_pct": _change(ratio),
                               "n_inputs_used": len(sides), "n_inputs_in_weights": len(listed[benchmark])})
    return benchmark_rows, input_rows
