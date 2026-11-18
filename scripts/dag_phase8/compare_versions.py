"""Render an audited native/DAG/calibrated comparison from actual experiment evidence.

This command recalculates errors and draws figures. It does not run a new model
simulation or substitute hardware measurements for the CPU reference experiment.
"""
import argparse
import csv
from datetime import datetime
from hashlib import sha256
from html import escape
import io
import json
import math
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/dag/phase8/artifacts/20261118-phase8-simulated-reference.zip"
VERSIONS = (
    ("old", "V0 原生基线", "V0 Native SimAI", "legacy", "analytical", "#3465a4"),
    ("same_cost", "V1 仅 DAG，同费用", "V1 DAG, same costs", "dag_expanded", "analytical", "#858d98"),
    ("revised_cost", "V2 改进版：DAG＋通信校准", "V2 Improved: DAG + calibration", "dag_expanded", "analytical", "#16856b"),
)
METRICS = (("E2E", "s"), ("TTFT", "ttft_s"), ("TPOT", "tpot_s"))


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(f"expected a project-relative evidence path: {name}")
    return path.as_posix()


class Evidence:
    """Read only manifest-checked artifacts; never extract the archive over source."""

    def __init__(self, *, archive=None, run_dir=None):
        self.archive = None
        self.cache = {}
        if archive:
            archive = Path(archive).resolve()
            expected = {line.split()[1]: line.split()[0]
                        for line in (archive.parent / "SHA256SUMS").read_text().splitlines() if line.strip()}
            actual = sha256(archive.read_bytes()).hexdigest()
            if expected.get(archive.name) != actual:
                raise ValueError("archive checksum does not match SHA256SUMS")
            self.archive = zipfile.ZipFile(archive)
            delivery = json.loads(self.archive.read("DELIVERY.json"))
            self.prefix = safe_name(delivery["result_path"])
            manifest_bytes = self.archive.read(self.prefix + "/run-manifest.json")
            if sha256(manifest_bytes).hexdigest() != delivery["manifest_sha256"]:
                self.archive.close()
                raise ValueError("delivery manifest checksum mismatch")
            self.identity = dict(kind="archived_simulation_evidence", archive=archive.name, sha256=actual)
        else:
            run_dir = Path(run_dir).resolve()
            if not run_dir.is_relative_to(ROOT / "results/dag/phase8") or run_dir == ROOT / "results/dag/phase8":
                raise ValueError("run directory must be below results/dag/phase8")
            self.prefix = run_dir.relative_to(ROOT).as_posix()
            manifest_bytes = (run_dir / "run-manifest.json").read_bytes()
            self.identity = dict(kind="local_simulation_evidence", path=self.prefix,
                                 manifest_sha256=sha256(manifest_bytes).hexdigest())
        if not self.prefix.startswith("results/dag/phase8/"):
            raise ValueError("unexpected experiment result path")
        self.manifest = json.loads(manifest_bytes)

    def close(self):
        if self.archive:
            self.archive.close()

    def artifact(self, name):
        name = safe_name(name)
        prefix = self.prefix + "/"
        if not name.startswith(prefix):
            raise ValueError("evidence is outside this experiment")
        relative = name[len(prefix):]
        expected = self.manifest["artifact_sha256"].get(relative)
        if expected is None:
            raise ValueError(f"artifact is not covered by the run manifest: {relative}")
        if name not in self.cache:
            payload = self.archive.read(name) if self.archive else (ROOT / name).read_bytes()
            if sha256(payload).hexdigest() != expected:
                raise ValueError(f"evidence checksum mismatch: {relative}")
            self.cache[name] = payload
        return self.cache[name]

    def read(self, relative):
        return self.artifact(self.prefix + "/" + relative)

    def json(self, relative):
        return json.loads(self.read(relative))


def number(value, *, positive=False):
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError("timing values must be finite and nonnegative; references must be positive")
    return result


def equal(left, right):
    return math.isclose(number(left), number(right), rel_tol=1e-10, abs_tol=1e-12)


def load_samples(evidence):
    report = evidence.json("simulation-report.json")
    if report["reference_nature"] != "simulated" or report["hardware_accuracy_claim"]:
        raise ValueError("this display is scoped to simulated communication references")
    specification = evidence.json("experiment.json")
    dataset = evidence.json("validation.json")
    planned = {sample["id"]: sample for sample in specification["samples"]}
    rows = list(csv.DictReader(io.StringIO(evidence.read("request-comparison.csv").decode("utf-8"))))
    if len(rows) != len(planned) or {row["sample"] for row in rows} != set(planned):
        raise ValueError("comparison must include every planned sample exactly once")
    pairs = {sample["group_id"]: sample for sample in dataset["samples"]}
    if len(pairs) != len(rows):
        raise ValueError("dataset sample coverage differs from the comparison table")
    if sha256(evidence.artifact(dataset["parameter_freeze"]["path"])).hexdigest() != dataset["parameter_freeze"]["sha256"]:
        raise ValueError("parameter freeze checksum mismatch")
    verified = []
    for raw in rows:
        sample = planned[raw["sample"]]
        if raw["split"] != sample["split"] or raw["split"] not in ("calibration", "validation"):
            raise ValueError("sample split differs from the frozen experiment")
        if any(number(raw[key]) != sample[key] for key in ("prefill_tokens", "decode_tokens")):
            raise ValueError("request shape differs from the experiment")
        pair = pairs.get("dense_tp8_" + raw["sample"])
        if pair is None or pair["split"] != raw["split"]:
            raise ValueError("sample is missing from the frozen accuracy dataset")
        values = {}
        identities = []
        for role, mode, backend in [("reference", "legacy", "ns3"),
                                     *((v[0], v[3], v[4]) for v in VERSIONS)]:
            record = json.loads(evidence.artifact(pair[role + "_record"]))
            for item in record["evidence"]:
                if sha256(evidence.artifact(item["path"])).hexdigest() != item["sha256"]:
                    raise ValueError("record evidence checksum mismatch")
            identities.append(tuple(record[key] for key in
                ("model", "hardware", "input_sha256", "topology_sha256", "tp", "pp", "ep", "dtype")))
            prediction = json.loads(evidence.artifact(record["run_id"] + "/prediction.json"))
            if (prediction["mode"], prediction["backend"]) != (mode, backend):
                raise ValueError("native/improved version label does not match the executed path")
            execution = json.loads(evidence.artifact(prediction["native"] + "/execution-summary.json"))
            if execution["status"] != "completed" or len(execution["requests"]) != 1:
                raise ValueError("CLI reference/prediction request did not complete")
            [request] = execution["requests"]
            if not request["completed"] or request["num_processed_tokens"] != sample["prefill_tokens"] + sample["decode_tokens"]:
                raise ValueError("CLI request token count differs from the planned input")
            [metrics] = list(csv.DictReader(io.StringIO(evidence.artifact(
                prediction["native"] + "/request_metrics.csv").decode("utf-8"))))
            actual = dict(s=request["completed_at"] - request["arrived_at"],
                          ttft_s=number(metrics["prefill_e2e_time"]),
                          tpot_s=number(metrics["decode_time_execution_plus_preemption_normalized"]))
            if record["raw_unit"] != "s" or record["conversion_to_s"] != 1 or not equal(record["raw_value"], actual["s"]):
                raise ValueError("record E2E value or unit differs from the actual CLI output")
            for _, suffix in METRICS:
                value = number(raw[role + "_" + suffix], positive=role == "reference")
                if not equal(value, actual[suffix]):
                    raise ValueError("comparison table differs from actual CLI request metrics")
                values[role + "_" + suffix] = value
        if len(set(identities)) != 1:
            raise ValueError("reference/native/improved model or workload identities differ")
        verified.append(dict(sample=raw["sample"], split=raw["split"],
                             prefill_tokens=sample["prefill_tokens"], decode_tokens=sample["decode_tokens"], **values))
    return verified, report, specification


def calculate(samples):
    """Exclude calibration, preserve regressions, and keep signed prediction bias."""
    validation = [sample for sample in samples if sample["split"] == "validation"]
    if not validation:
        raise ValueError("no validation samples")
    details, summary = [], []
    for metric, suffix in METRICS:
        for role, label, _, _, _, _ in VERSIONS:
            subset = []
            for sample in validation:
                reference = number(sample["reference_" + suffix], positive=True)
                prediction = number(sample[role + "_" + suffix])
                bias = prediction - reference
                native_error = abs(number(sample["old_" + suffix]) - reference)
                absolute = abs(bias)
                difference = native_error - absolute
                outcome = "tied" if abs(difference) <= 1e-12 else ("improved" if difference > 0 else "regressed")
                row = dict(sample=sample["sample"], metric=metric, version=role, label=label,
                           reference_ms=reference * 1000, prediction_ms=prediction * 1000,
                           signed_bias_ms=bias * 1000, absolute_error_ms=absolute * 1000,
                           relative_error_percent=absolute / reference * 100, outcome_vs_native=outcome)
                subset.append(row)
                details.append(row)
            summary.append(dict(metric=metric, version=role, label=label, samples=len(subset),
                mae_ms=math.fsum(row["absolute_error_ms"] for row in subset) / len(subset),
                mean_relative_error_percent=math.fsum(row["relative_error_percent"] for row in subset) / len(subset),
                **{name: sum(row["outcome_vs_native"] == name for row in subset)
                   for name in ("improved", "tied", "regressed")}))
    return details, summary


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def draw(output, samples, summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    validation = [s for s in samples if s["split"] == "validation"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none"})
    fig, (left, right) = plt.subplots(1, 2, figsize=(13.5, 5.8))
    x = list(range(len(validation)))
    left.plot(x, [s["reference_s"] * 1000 for s in validation], "k--", marker="D", label="ns-3 communication reference", zorder=5)
    for role, _, label, _, _, color in VERSIONS:
        left.plot(x, [s[role + "_s"] * 1000 for s in validation], marker="o" if role != "same_cost" else "x",
                  linestyle=":" if role == "same_cost" else "-", color=color, label=label)
    left.set_xticks(x, [f"{s['prefill_tokens']}/{s['decode_tokens']}" for s in validation])
    left.set(xlabel="Request: Prefill / Decode tokens", ylabel="Predicted request E2E (ms)",
             title="Request predictions: closer to reference is better", ylim=(0, None))
    left.legend(loc="upper left", fontsize=8)
    names = [name for name, _ in METRICS]
    for index, (role, _, label, _, _, color) in enumerate(VERSIONS):
        values = [next(row["mean_relative_error_percent"] for row in summary
                       if row["metric"] == name and row["version"] == role) for name in names]
        bars = right.bar([i + (index - 1) * .25 for i in range(len(names))], values, width=.24,
                         color=color, label=label)
        right.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    right.set_xticks(range(len(names)), names)
    right.set(ylabel="Mean absolute relative error (%)", title="Validation errors: lower is better", ylim=(0, None))
    right.margins(y=.18)
    right.legend(loc="upper left", fontsize=8)
    for axis in (left, right):
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=.18)
        axis.set_axisbelow(True)
    fig.suptitle("Native vs improved SimAI | controlled CPU simulation", fontsize=15)
    fig.text(.5, .03, f"Shared synthetic compute + original scheduler | {len(validation)} validation requests | Changed factor: communication cost calibration",
             ha="center", fontsize=9, color="#475569")
    fig.tight_layout(rect=(0, .06, 1, .94))
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output / ("version-comparison." + suffix), dpi=180, metadata={"Creator": "SimAI compare_versions.py"})
    svg = output / "version-comparison.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n",
                   encoding="utf-8", newline="\n")
    plt.close(fig)


def report_text(samples, summary, identity):
    validation_count = sum(sample["split"] == "validation" for sample in samples)
    lines = ["# 原生与改进版 SimAI：仿真误差对照", "",
        "本报告由脚本从经过哈希核验的实际 CLI 输出重新计算；只统计 validation，校准样本单列。", "",
        "| 标记 | 执行路径 | 费用模型 |", "|---|---|---|",
        "| 参考 | legacy + simai_simulation | ns-3 通信参考，共享合成计算画像 |",
        "| V0 原生基线 | legacy + simai_analytical | 未校准；指本仓库的原有执行路径 |",
        "| V1 仅 DAG | dag_expanded + simai_analytical | 与 V0 相同，用于隔离 DAG 时序影响 |",
        "| V2 改进版 | dag_expanded + simai_analytical | DAG＋仅由校准请求拟合的通信固定开销 |", "",
        "![预测值与误差对比](version-comparison.png)", "",
        "## 验证集汇总", "", "| 指标 | 版本 | 样本数 | 平均相对误差 | MAE/ms | 改善/持平/退化（相对 V0） |",
        "|---|---|---:|---:|---:|---|"]
    for row in summary:
        lines.append(f"| {row['metric']} | {row['label']} | {row['samples']} | {row['mean_relative_error_percent']:.2f}% | {row['mae_ms']:.3f} | {row['improved']}/{row['tied']}/{row['regressed']} |")
    lines += ["", "## 逐请求 E2E", "", "| 分组 | Prefill/Decode | 参考/ms | V0 原生/ms | V1 仅DAG/ms | V2 改进/ms |", "|---|---|---:|---:|---:|---:|"]
    for sample in samples:
        lines.append(f"| {sample['split']} | {sample['prefill_tokens']}/{sample['decode_tokens']} | " +
                     " | ".join(f"{sample[role + '_s'] * 1000:.3f}" for role in ("reference", "old", "same_cost", "revised_cost")) + " |")
    lines += ["", "## 如何理解", "",
        "相对误差 = |预测值 − 参考值| / 参考值；先逐样本计算，再取验证集平均，不使用校准行。",
        "V0/V1 几乎重合；本轮 V2 的误差变化来自通信费用校准，不能归因为 DAG 调度带来的精度提升。",
        "预测更接近参考代表误差降低；预测时长变大不代表实际程序运行变慢。",
        "这不是原封不动的上游版本与新版本的跨提交测试：V0 是当前仓库保留的 legacy 路径。", "",
        "限定范围：Llama-2-7b 结构、逻辑8×H20、TP8/PP1、单请求，固定合成计算与原调度器。",
        "ns-3 是通信模拟参考；本报告不验证真实 GPU、计算画像、调度器、PD、MoE 或联合场景的精度。",
        f"验证 Prefill 大小与请求输入留出，Decode 通信输入共享；样本量为{validation_count}个，不作广泛泛化结论。", "",
        "脚本只读取证据并重新计算/绘图；不会重跑模型仿真，也不会修改冻结参数。", "",
        "证据身份：`" + json.dumps(identity, ensure_ascii=False) + "`。"]
    return "\n".join(lines) + "\n"


def write_html(output, markdown, summary, samples):
    def table(headers, rows):
        return "<table><thead><tr>" + "".join("<th>" + escape(h) + "</th>" for h in headers) + "</tr></thead><tbody>" + "".join(
            "<tr>" + "".join("<td>" + escape(str(cell)) + "</td>" for cell in row) + "</tr>" for row in rows) + "</tbody></table>"
    metrics = table(["指标", "版本", "验证样本", "平均相对误差", "MAE/ms", "改善/持平/退化"],
        [[r["metric"], r["label"], r["samples"], f"{r['mean_relative_error_percent']:.2f}%", f"{r['mae_ms']:.3f}",
          f"{r['improved']}/{r['tied']}/{r['regressed']}"] for r in summary])
    requests = table(["分组", "Prefill/Decode", "参考/ms", "V0 原生/ms", "V1 仅DAG/ms", "V2 改进/ms"],
        [[r["split"], f"{r['prefill_tokens']}/{r['decode_tokens']}",
          *[f"{r[role + '_s'] * 1000:.3f}" for role in ("reference", "old", "same_cost", "revised_cost")]] for r in samples])
    svg = (output / "version-comparison.svg").read_text(encoding="utf-8")
    svg = svg[svg.index("<svg"):]
    html = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>原生与改进版 SimAI 误差对照</title>
<style>body{font:16px/1.7 system-ui,'Microsoft YaHei',sans-serif;color:#172536;max-width:1200px;margin:36px auto;padding:0 24px;background:#f6f8fb}h1{font-size:28px}table{border-collapse:collapse;width:100%;background:white;margin:20px 0}td,th{padding:10px 12px;border:1px solid #d9e0e8;text-align:left}th{background:#eaf0f7}svg{max-width:100%;height:auto}pre{white-space:pre-wrap;background:white;padding:20px;border:1px solid #d9e0e8}p{max-width:1000px}</style>
<h1>原生与改进版 SimAI：仿真误差对照</h1>
<p><b>V0 原生基线</b>：本仓库 legacy＋analytical，未校准。<b>V1 仅DAG</b>：与V0同费用的DAG对照。<b>V2 改进版</b>：DAG＋冻结通信费用校准。<b>参考</b>：ns-3通信模拟，共享合成计算与原调度器。</p>
<p>TP8稠密单请求受控实验；仅统计验证请求。收益来自通信费用校准，尚未证明真实硬件或PD/MoE精度。</p>""" + svg + "<h2>验证集汇总</h2>" + metrics + "<h2>逐请求预测</h2>" + requests + "<h2>完整说明与证据身份</h2><pre>" + escape(markdown) + "</pre></html>"
    (output / "report.html").write_text(html, encoding="utf-8", newline="\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--archive", type=Path, help="Evidence ZIP with adjacent SHA256SUMS (default: committed phase8 archive)")
    source.add_argument("--run-dir", type=Path, help="Existing completed simulation experiment below results/dag/phase8")
    parser.add_argument("--output", type=Path, help="New report directory below results/dag/phase8")
    args = parser.parse_args(argv)
    output = (ROOT / (args.output or Path("results/dag/phase8") / ("version-comparison-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")))).resolve()
    if output == ROOT / "results/dag/phase8" or not output.is_relative_to(ROOT / "results/dag/phase8"):
        parser.error("output must be a new directory below results/dag/phase8")
    evidence = Evidence(run_dir=ROOT / args.run_dir) if args.run_dir else Evidence(archive=ROOT / (args.archive or ARCHIVE))
    try:
        samples, _, _ = load_samples(evidence)
        details, summary = calculate(samples)
        output.mkdir(parents=True, exist_ok=False)
        draw(output, samples, summary)
        write_csv(output / "per-sample-errors.csv", details)
        write_csv(output / "metric-summary.csv", summary)
        markdown = report_text(samples, summary, evidence.identity)
        (output / "report.md").write_text(markdown, encoding="utf-8", newline="\n")
        write_html(output, markdown, summary, samples)
        files = {p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
        manifest = dict(source=evidence.identity, script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                        evidence_files_verified=len(evidence.cache), validation_samples=sum(s["split"] == "validation" for s in samples),
                        hardware_accuracy_claim=False, simulation_rerun=False, artifact_sha256=files)
        (output / "display-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"Report: {output / 'report.html'}")
        for metric, _ in METRICS:
            native, improved = [next(r for r in summary if r["metric"] == metric and r["version"] == role)
                                for role in ("old", "revised_cost")]
            print(f"{metric}: V0 {native['mean_relative_error_percent']:.2f}% -> V2 {improved['mean_relative_error_percent']:.2f}%")
        return 0
    finally:
        evidence.close()


if __name__ == "__main__":
    raise SystemExit(main())
