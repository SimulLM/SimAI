"""Display the same-cost mechanism experiment, distinct from cost calibration."""
import argparse
import csv
from hashlib import sha256
from html import escape
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.dag_phase8.compare_versions import Evidence

ARCHIVE = ROOT / "docs/dag/phase8/artifacts/20261119-phase8-dag-mechanism.zip"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--run-dir", type=Path)
    source.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if output == ROOT / "results/dag/phase8" or not output.is_relative_to(ROOT / "results/dag/phase8"):
        parser.error("output must be a new directory below results/dag/phase8")
    evidence = Evidence(run_dir=ROOT / args.run_dir) if args.run_dir else Evidence(archive=ROOT / (args.archive or ARCHIVE))
    try:
        report = evidence.json("mechanism-report.json")
        if report["calibration_used"] or report["fitted_parameters"] != 0 or not report["same_cost_verified"]:
            raise ValueError("this display requires the zero-fit same-cost experiment")
        rows = list(csv.DictReader(io.StringIO(evidence.read("request-comparison.csv").decode("utf-8"))))
        summaries = list(csv.DictReader(io.StringIO(evidence.read("case-summary.csv").decode("utf-8"))))
        for summary in summaries:
            group = [row for row in rows if row["case"] == summary["case"]]
            if len(group) != int(summary["requests"]):
                raise ValueError("incomplete displayed sample coverage")
            for prefix, column in (("legacy", "legacy_e2e_s"), ("dag", "dag_expanded_e2e_s")):
                mean = math.fsum(abs(float(row[column])-float(row["reference_e2e_s"]))/float(row["reference_e2e_s"])
                                 for row in group)/len(group)
                if not math.isclose(mean, float(summary[prefix+"_mean_relative_error"]), abs_tol=1e-12):
                    raise ValueError("displayed error differs from raw request values")
        output.mkdir(parents=True, exist_ok=False)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "none"})
        fig, (left, right) = plt.subplots(1, 2, figsize=(14, 5.8))
        names = [row["case"] for row in summaries]
        x = list(range(len(names)))
        for role, offset, color, label in (("legacy", -.18, "#3465a4", "Native legacy"),
                                           ("dag", .18, "#16856b", "DAG, identical costs")):
            bars = left.bar([i+offset for i in x], [100*float(row[role+"_mean_relative_error"]) for row in summaries],
                            width=.34, color=color, label=label)
            left.bar_label(bars, fmt="%.2f", fontsize=7, padding=3)
        left.set_xticks(x, names, rotation=25, ha="right", fontsize=8)
        left.set(title="Error relative to independent FCFS reference", ylabel="Mean request E2E relative error (%)", ylim=(0, None))
        left.legend(loc="upper left", fontsize=8)
        left.margins(y=.2)
        group = [row for row in rows if row["case"] == "shared-eight"]
        ids = [int(row["request_id"]) for row in group]
        for field, label, color, style in (("reference_e2e_s", "Independent FCFS reference", "black", "--"),
            ("legacy_e2e_s", "Native legacy", "#3465a4", "-"),
            ("dag_expanded_e2e_s", "DAG, identical costs", "#16856b", ":")):
            right.plot(ids, [1000*float(row[field]) for row in group], linestyle=style, marker="o", label=label, color=color)
        right.set(title="Eight replicas sharing one endpoint", xlabel="Request / replica index", ylabel="Predicted request E2E (ms)", ylim=(0,None))
        right.legend(fontsize=8)
        for axis in (left, right):
            axis.spines[["top", "right"]].set_visible(False)
            axis.grid(axis="y", alpha=.18)
            axis.set_axisbelow(True)
        fig.suptitle("DAG mechanism contribution | unchanged service costs, zero calibration", fontsize=15)
        fig.text(.5, .025, "Controlled synthetic PP2 benchmark | serialized endpoint assumption | independent queueing reference, not hardware accuracy", ha="center", fontsize=9)
        fig.tight_layout(rect=(0,.06,1,.94))
        for suffix in ("png","svg","pdf"):
            fig.savefig(output/("dag-mechanism."+suffix), dpi=180, metadata={"Creator":"SimAI mechanism_display.py"})
        plt.close(fig)
        svg = output/"dag-mechanism.svg"
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8",newline="\n")
        text = ["# 同费用下的 DAG 机制贡献", "", "原生 legacy 与 DAG 使用完全相同的预测器费用；不做通信费用校准。",
            "参考为独立的FCFS共享端点排队模型，不读取DAG图或执行时间线。", "",
            "![同费用机制对照](dag-mechanism.png)", "",
            "| 场景 | 类别 | 请求数 | 原生平均相对误差 | DAG平均相对误差 | 最大参考等待/ms | 改善/持平/退化 |",
            "|---|---|---:|---:|---:|---:|---|"]
        for row in summaries:
            text.append(f"| {row['case']} | {row['role']} | {row['requests']} | {100*float(row['legacy_mean_relative_error']):.4f}% | "
                f"{100*float(row['dag_mean_relative_error']):.4f}% | {1000*float(row['max_reference_wait_s']):.4f} | "
                f"{row['improved']}/{row['tied']}/{row['regressed']} |")
        text += ["", f"主要验证集：{report['validation_requests']}个请求，原生平均相对误差{100*report['legacy_mean_relative_error']:.4f}%，"
                 f"DAG为{100*report['dag_mean_relative_error']:.4f}%。", "",
                 "收益来自共享端点等待进入DAG时间推进；未调整任何计算/通信服务耗时。",
                 "这证明相对于明确排队假设的机制一致性，不证明真实GPU或包级网络预测精度。",
                 "单请求/独立端点/充分错峰为对照；所有预先指定的样本均保留。"]
        markdown="\n".join(text)+"\n"
        (output/"report.md").write_text(markdown,encoding="utf-8",newline="\n")
        svg_text=svg.read_text(encoding="utf-8"); svg_text=svg_text[svg_text.index("<svg"):]
        html='<!doctype html><meta charset="utf-8"><title>同费用DAG机制对照</title><style>body{font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#172536}svg{max-width:100%;height:auto}pre{white-space:pre-wrap;background:#f3f6fa;padding:20px}</style><h1>同费用DAG机制贡献：原生与DAG对照</h1><p>相同服务费用、零校准；独立FCFS排队参考。明确的共享端点等待进入仿真，不等同于硬件精度验证。</p>'+svg_text+'<pre>'+escape(markdown)+'</pre>'
        (output/"report.html").write_text(html,encoding="utf-8",newline="\n")
        metadata=dict(source=evidence.identity, calibration_used=False,
            script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            artifact_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()})
        (output/"display-manifest.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8",newline="\n")
        print(output/"report.html")
    finally:
        evidence.close()


if __name__ == "__main__":
    main()
