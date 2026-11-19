"""Render verified native / submission-DAG / FCFS-DAG comparisons."""
import argparse
import csv
from hashlib import sha256
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("expanded", "original", "holdout", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT/"results/dag/phase8" or not output.is_relative_to(ROOT/"results/dag/phase8"):
        parser.error("output must be a new directory below results/dag/phase8")
    data = {}
    inputs = {}
    for name in ("expanded", "original", "holdout"):
        folder = getattr(args, name).resolve()
        manifest = json.loads((folder/"manifest.json").read_text())
        for file, digest in manifest["artifact_sha256"].items():
            assert sha256((folder/file).read_bytes()).hexdigest() == digest
        report = json.loads((folder/"comparison-report.json").read_text())
        assert report["passed"] and report["audit"]["passed"]
        rows = list(csv.DictReader((folder/"request-comparison.csv").open(encoding="utf-8")))
        assert len(rows) == report["requests"]
        data[name] = (report, rows, list(csv.DictReader((folder/"case-comparison.csv").open(encoding="utf-8"))))
        inputs[name] = dict(path=str(folder.relative_to(ROOT)), manifest_sha256=sha256((folder/"manifest.json").read_bytes()).hexdigest())
    output.mkdir(parents=True, exist_ok=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":9, "svg.fonttype":"none"})
    report, rows, cases = data["expanded"]
    series = (("native", "Native legacy", "#3465a4"), ("submission", "DAG before: submission priority", "#c67c32"),
              ("fcfs", "DAG after: ready-time FCFS", "#16856b"))
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    metrics = (("mean_relative_error", "Mean"), ("p95_relative_error", "P95"), ("max_relative_error", "Maximum"))
    for index, (key, label, color) in enumerate(series):
        axes[0,0].bar([i+(index-1)*.24 for i in range(3)],
                      [100*report["statistics"][key][metric] for metric,_ in metrics], width=.23, label=label, color=color)
    axes[0,0].set(xticks=range(3), xticklabels=[label for _,label in metrics], ylabel="Relative error (%)",
                  title="Expanded suite: 262 validation requests vs unchanged FCFS reference")
    axes[0,0].legend(fontsize=8)
    validation = [case for case in cases if case["role"] == "validation"]
    labels = [c["case"].replace("order-random-202611", "seed-").replace("order-", "") for c in validation]
    for key,label,color in series:
        axes[0,1].plot(range(len(validation)), [100*float(c[key+"_mean_relative_error"]) for c in validation],
                       marker="o", markersize=3, label=label, color=color)
    axes[0,1].set(xticks=range(len(labels)), xticklabels=labels, ylabel="Mean relative error (%)", title="Every validation case retained")
    axes[0,1].tick_params(axis="x", labelrotation=65, labelsize=7)
    worst = report["previous_worst_request"]
    part = [r for r in rows if r["case"] == worst["case"]]
    ids = [int(r["request_id"]) for r in part]
    for key,label,color in series:
        axes[1,0].plot(ids, [1000*float(r[key+"_e2e_s"]) for r in part], marker="o", markersize=3, color=color, label=label)
    axes[1,0].plot(ids, [1000*float(r["reference_e2e_s"]) for r in part], color="black", linestyle="--", label="Independent FCFS reference")
    axes[1,0].set(xlabel="Request index", ylabel="Request E2E (ms)", title="Previous worst case: "+worst["case"])
    axes[1,0].legend(fontsize=8)
    for index,(key,label,color) in enumerate(series):
        axes[1,1].bar([i+(index-1)*.24 for i in ids], [100*float(r[key+"_relative_error"]) for r in part],
                      width=.23, color=color, label=label)
    axes[1,1].set(xlabel="Request index", ylabel="Relative error (%)", title="Per-request errors: no regressions hidden by averaging")
    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=.18); axis.set_axisbelow(True)
    fig.suptitle("FCFS queue-policy repair | unchanged workloads, costs and primary reference", fontsize=15)
    fig.text(.5, .015, "Synthetic CPU simulation; errors are against a fixed queue model, not measured GPU accuracy", ha="center")
    fig.tight_layout(rect=(0,.035,1,.95))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(output/("dag-fcfs-fix."+ext), dpi=180, metadata={"Creator":"SimAI FCFS comparison"})
    plt.close(fig)
    svg_path=output/"dag-fcfs-fix.svg"
    svg_path.write_text("\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8",newline="\n")
    text = ["# FCFS 排队策略修复实验", "", "原生、修复前 DAG 与修复后 DAG 使用相同服务费用。主要参考始终为独立 FCFS 模拟。", "",
            "| 数据集 | 请求数（验证/对照） | 原生平均误差 | 修复前 DAG | FCFS DAG | 相对旧 DAG 改善/持平/退化（全部请求） |",
            "|---|---:|---:|---:|---:|---|"]
    for name,title in (("expanded","原23场景"),("original","原7场景"),("holdout","新增8场景")):
        r=data[name][0]; s=r["statistics"]; c=r["vs_previous_all"]
        text.append(f"| {title} | {r['requests']}（{r['validation_requests']}/{r['control_requests']}） | {100*s['native']['mean_relative_error']:.4f}% | {100*s['submission']['mean_relative_error']:.4f}% | {100*s['fcfs']['mean_relative_error']:.4f}% | {c.get('improved',0)}/{c.get('tied',0)}/{c.get('regressed',0)} |")
    text += ["",f"原最坏请求：{worst['case']} / {worst['request_id']}，修复前误差 {100*worst['submission_relative_error']:.4f}%，修复后 {100*worst['fcfs_relative_error']:.4f}%。", "",
             "误差接近零表示同假设排队模型的一致性，不表示真实 GPU 仿真误差为零。FCFS 改变服务顺序，部分请求预测耗时会变长；逐请求误差均未退化。提交优先级仍为默认兼容策略。", "",
             "![三版本对照](dag-fcfs-fix.png)", "", "输入身份：", "", json.dumps(inputs,ensure_ascii=False,indent=2)]
    (output/"report.md").write_text("\n".join(text)+"\n",encoding="utf-8",newline="\n")
    svg=svg_path.read_text(encoding="utf-8"); svg=svg[svg.index("<svg"):]
    table_rows=[line for line in text if line.startswith("| ") and not line.startswith("|---")]
    table="<table>"+"".join("<tr>"+"".join(("<th>" if i==0 else "<td>")+escape(cell.strip())+("</th>" if i==0 else "</td>")
        for cell in line.strip("|").split("|"))+"</tr>" for i,line in enumerate(table_rows))+"</table>"
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>FCFS 排队策略修复实验</title><style>body{max-width:1400px;margin:36px auto;padding:0 20px;font:16px/1.7 system-ui;color:#17212b}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap}svg{width:100%;height:auto}</style><h1>FCFS 排队策略修复实验</h1><p>'+escape(text[2])+"</p>"+table+"<p>"+escape(text[-9])+"</p><p>"+escape(text[-7])+"</p>"+svg+"<h2>输入证据身份</h2><pre>"+escape(json.dumps(inputs,ensure_ascii=False,indent=2))+"</pre></html>"
    (output/"dag-fcfs-fix.html").write_text(page,encoding="utf-8",newline="\n")
    manifest=dict(inputs=inputs,source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  artifact_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in output.iterdir()})
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8",newline="\n")


if __name__ == "__main__":
    main()
