"""Display expanded mechanism sensitivity, preserving FCFS disagreements and regressions."""
import argparse
import csv
from hashlib import sha256
from html import escape
import io
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.dag_phase8.compare_versions import Evidence

ARCHIVE=ROOT/"docs/dag/phase8/artifacts/20261119-phase8-dag-mechanism-expanded.zip"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group()
    source.add_argument("--run-dir",type=Path)
    source.add_argument("--archive",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    output=(ROOT/args.output).resolve()
    if output==ROOT/"results/dag/phase8" or not output.is_relative_to(ROOT/"results/dag/phase8"):
        parser.error("output must be a new directory below results/dag/phase8")
    evidence=Evidence(run_dir=ROOT/args.run_dir) if args.run_dir else Evidence(archive=ROOT/(args.archive or ARCHIVE))
    try:
        report=evidence.json("mechanism-report.json")
        spec=evidence.json("experiment.json")
        rows=list(csv.DictReader(io.StringIO(evidence.read("request-comparison.csv").decode())))
        cases=list(csv.DictReader(io.StringIO(evidence.read("case-summary.csv").decode())))
        groups=list(csv.DictReader(io.StringIO(evidence.read("group-summary.csv").decode())))
        expected={case["name"]:case for case in spec["cases"]}
        if {case["case"] for case in cases}!=set(expected) or len(rows)!=sum(len(case["tokens"]) for case in spec["cases"]):
            raise ValueError("planned samples missing from display")
        for case in cases:
            samples=[row for row in rows if row["case"]==case["case"]]
            if len(samples)!=len(expected[case["case"]]["tokens"]):raise ValueError("sample count mismatch")
            for role,column in (("legacy","legacy_e2e_s"),("dag","dag_expanded_e2e_s")):
                actual=math.fsum(abs(float(row[column])-float(row["reference_e2e_s"]))/float(row["reference_e2e_s"]) for row in samples)/len(samples)
                if not math.isclose(actual,float(case[role+"_mean_relative_error"]),abs_tol=1e-12):raise ValueError("score mismatch")
        if report["calibration_used"] or not report["same_cost_verified"]:raise ValueError("same-cost experiment required")
        output.mkdir(parents=True,exist_ok=False)
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"svg.fonttype":"none"})
        series=(("legacy_mean_relative_error","Native vs FCFS","#3465a4"),
                ("dag_mean_relative_error","DAG vs FCFS","#16856b"),
                ("dag_priority_mean_relative_error","DAG vs submission priority","#9863b8"))
        fig,axes=plt.subplots(2,2,figsize=(14,9))
        def bars(axis,items,labels,title):
            for index,(field,label,color) in enumerate(series):
                axis.bar([i+(index-1)*.24 for i in range(len(items))],
                         [100*float(item[field]) for item in items],width=.23,color=color,label=label)
            axis.set_xticks(range(len(items)),labels,rotation=15,ha="right")
            axis.set(title=title,ylabel="Mean relative error (%)",ylim=(0,None))
        bars(axes[0,0],groups,[row["family"] for row in groups],"Workload families (all requests retained)")
        scale=[row for row in cases if row["family"]=="scale"]
        for field,label,color in series:
            axes[0,1].plot([int(row["requests"]) for row in scale],[100*float(row[field]) for row in scale],marker="o",label=label,color=color)
        axes[0,1].set(title="Concurrent request scale",xlabel="Requests / logical replicas",ylabel="Mean relative error (%)",ylim=(0,None))
        arrival=[row for row in cases if row["family"]=="arrival"]
        bars(axes[1,0],arrival,[f"{expected[row['case']]['arrival_gap_s']*1e6:g} us" for row in arrival],"Interarrival sensitivity (16 requests)")
        ordering=[row for row in cases if row["family"]=="ordering"]
        labels=[row["case"].replace("order-","").replace("random-202611","seed-") for row in ordering]
        bars(axes[1,1],ordering,labels,"Mixed lengths and ordering: policy sensitivity")
        for axis in axes.flat:
            axis.spines[["top","right"]].set_visible(False);axis.grid(axis="y",alpha=.18);axis.set_axisbelow(True)
        axes[0,0].legend(fontsize=8)
        fig.suptitle("Expanded same-cost DAG experiment | predeclared FCFS + submission-priority references",fontsize=14)
        fig.text(.5,.018,"Deterministic synthetic PP2 model; no cost calibration, GPU measurements or packet-level accuracy claim",ha="center",fontsize=9)
        fig.tight_layout(rect=(0,.04,1,.95))
        def export(figure,name):
            for ext in ("png","svg","pdf"):figure.savefig(output/(name+"."+ext),dpi=180,metadata={"Creator":"SimAI expanded mechanism display"})
            path=output/(name+".svg")
            path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8",newline="\n")
        export(fig,"dag-mechanism-expanded");plt.close(fig)
        worst=max((case for case in cases if case["role"]=="validation"),key=lambda case:float(case["dag_mean_relative_error"]))
        samples=[row for row in rows if row["case"]==worst["case"]]
        figure,(left,right)=plt.subplots(1,2,figsize=(14,5.5))
        ids=[int(row["request_id"]) for row in samples]
        for field,label,color,style in (("reference_e2e_s","FCFS reference","black","--"),
            ("priority_reference_e2e_s","Submission-priority reference","#9863b8",":"),
            ("legacy_e2e_s","Native legacy","#3465a4","-"),("dag_expanded_e2e_s","DAG","#16856b","-")):
            left.plot(ids,[1000*float(row[field]) for row in samples],marker="o",markersize=3,label=label,color=color,linestyle=style)
        left.set(title="Largest DAG FCFS error: "+worst["case"],xlabel="Request index",ylabel="Predicted E2E (ms)")
        left.legend(fontsize=8)
        for mode,offset,color,label in (("legacy",-.18,"#3465a4","Native vs FCFS"),("dag_expanded",.18,"#16856b","DAG vs FCFS")):
            colors=["#c54242" if mode=="dag_expanded" and row["outcome"]=="regressed" else color for row in samples]
            right.bar([i+offset for i in ids],[100*float(row[mode+"_relative_error"]) for row in samples],width=.34,color=color,label=label)
            for bar,chosen in zip(right.containers[-1],colors):bar.set_color(chosen)
        right.set(title="Per-request errors (red: DAG regresses vs FCFS)",xlabel="Request index",ylabel="Relative error (%)")
        right.legend(fontsize=8)
        for axis in (left,right):axis.spines[["top","right"]].set_visible(False);axis.grid(axis="y",alpha=.18);axis.set_axisbelow(True)
        figure.tight_layout();export(figure,"dag-mechanism-policy");plt.close(figure)
        text=["# 扩展同费用DAG机制实验", "",f"{len(cases)}个场景，{len(rows)}个请求：{report['validation_requests']}验证、{report['control_requests']}对照。", "",
              "FCFS为主要参考；提交优先级参考在运行前同时冻结，仅用于诊断策略差异。没有更改DAG执行器或费用。", "",
              "![扩展实验](dag-mechanism-expanded.png)","", "![最差FCFS场景](dag-mechanism-policy.png)","",
              "| 场景 | 类别 | 请求数 | 原生/FCFS | DAG/FCFS | DAG/提交优先级 | 改善/持平/退化 |",
              "|---|---|---:|---:|---:|---:|---|"]
        for case in cases:
            text.append(f"| {case['case']} | {case['role']} | {case['requests']} | {100*float(case['legacy_mean_relative_error']):.4f}% | "
                f"{100*float(case['dag_mean_relative_error']):.4f}% | {100*float(case['dag_priority_mean_relative_error']):.4f}% | "
                f"{case['improved']}/{case['tied']}/{case['regressed']} |")
        text += ["",f"按请求汇总的主要误差：原生{100*report['legacy_mean_relative_error']:.4f}%，DAG{100*report['dag_mean_relative_error']:.4f}%。",
                 f"按场景等权的主要误差：原生{100*report['validation_case_macro_mean_relative_error']['legacy']:.4f}%，DAG{100*report['validation_case_macro_mean_relative_error']['dag']:.4f}%。",
                 f"逐请求结果：{report['outcomes']}。FCFS未匹配请求{report['fcfs_mismatched_requests']}；提交优先级未匹配请求{report['priority_mismatched_requests']}。", "",
                 "确定性构造请求共享端点，不能视为独立硬件测量样本；P95是误差分布分位数，不是置信区间。",
                 "必须同时保留退化和策略不匹配，不能用次要参考替换FCFS主指标来宣称零误差。"]
        markdown="\n".join(text)+"\n";(output/"report.md").write_text(markdown,encoding="utf-8",newline="\n")
        images=[]
        for name in ("dag-mechanism-expanded","dag-mechanism-policy"):
            svg=(output/(name+".svg")).read_text(encoding="utf-8");images.append(svg[svg.index("<svg"):])
        html='<!doctype html><meta charset="utf-8"><title>扩展DAG机制实验</title><style>body{font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif;max-width:1200px;margin:32px auto;padding:0 20px;color:#172536}svg{max-width:100%;height:auto}pre{white-space:pre-wrap;background:#f3f6fa;padding:20px}</style><h1>扩展同费用DAG机制实验</h1><p>主要参考保持FCFS；次要提交优先级参考提前冻结，退化与不匹配均保留。CPU合成模型，不代表真实硬件精度。</p>'+''.join(images)+'<pre>'+escape(markdown)+'</pre>'
        (output/"report.html").write_text(html,encoding="utf-8",newline="\n")
        manifest=dict(source=evidence.identity,script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                      artifact_sha256={p.name:sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()})
        (output/"display-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8",newline="\n")
        print(output/"report.html")
    finally:evidence.close()


if __name__=="__main__":main()
