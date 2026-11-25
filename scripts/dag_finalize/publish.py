"""Publish immutable finalization evidence with strict hashes; no Git staging."""
import argparse
import csv
from hashlib import sha1
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0,str(ROOT))
from scripts.dag_finalize.common import read,save,digest,result_path


def excluded(path):
    return any(p in ('predictor-cache','prediction-cache','pytest-tmp','__pycache__') or 'pytest-tmp' in p for p in path.parts)


def publish(out,environment,prior_attempts=()):
    out=result_path(out);doc=ROOT/'docs/dag/finalize';doc.mkdir(parents=True,exist_ok=True)
    report=read(out/'acceptance-report.json')
    attempts=[]
    for attempt_index,previous in enumerate(prior_attempts,1):
        previous=result_path(previous)
        if previous==out or out.is_relative_to(previous) or previous.is_relative_to(out):raise ValueError('invalid prior-attempt nesting')
        prior=read(previous/'acceptance-report.json')
        # Keep the ordinal short: repeating the long run_id exceeds MAX_PATH
        # for archived native metric filenames. Original identity stays below.
        target=out/'prior-attempts'/f'{attempt_index:02d}'
        shutil.copytree(previous,target,ignore=shutil.ignore_patterns('predictor-cache','pytest-tmp','__pycache__'))
        attempts.append(dict(run_id=previous.name,exit_code=prior['exit_code'],functional_status=prior['functional_status'],
            regression=prior.get('regression'),error=prior.get('error'),retained_path=target.relative_to(out).as_posix()))
    if report['functional_status']!='passed':raise ValueError('cannot publish a failed run as accepted')
    source_audit=read(out/'source-audit.json');replay=read(out/'reproduction-report.json')
    independent=read(out/'independent-output-audit.json')
    if source_audit['status']!='passed' or replay['status']!='passed' or not independent['passed']:raise ValueError('mandatory verification is incomplete')
    traces=read(out/'deepseek-analysis.json');dense=read(out/'dense/simulation-report.json')
    policies={name:read(out/('policy-'+name)/'comparison/comparison-report.json') for name in ('original','expanded','holdout')}
    total={k:sum(p.get('vs_previous_all',{}).get(k,0) for p in policies.values()) for k in ('improved','tied','regressed')}
    linux=read(out/'linux-replay/acceptance-report.json')
    if not (out/'environment-evidence').exists():shutil.copytree(environment,out/'environment-evidence')
    before=read(out/'identity-before.json')
    consolidation=dict(schema_version='1.0',run_id=out.name,branch=before['branch']['stdout'].strip(),base_commit=before['head']['stdout'].strip(),
        source_identity='Base Git commit + recorded working-tree diff + exact runtime-source.zip; no claim that HEAD alone contains pending changes.',
        engineering_closeout='passed',reproduction_confirmation=replay,
        full_scope_request_accuracy=report['full_scope_accuracy'],overall_project_acceptance=report['overall_project_acceptance'],
        hardware_accuracy_claim=False,formal_exit_code=report['exit_code'],
        regression_windows=report['regression'],regression_linux=read(out/'linux-regression/process-result.json'),
        deepseek_admission={name:{k:r[k] for k in ('admission','numeric_accuracy_status','request_e2e_eligible','kernel_events','fractional_events_preserved','distributed_info')} for name,r in traces['traces'].items()},
        controlled_mechanism=read(out/'controlled/mechanism-consistency.json'),
        dense_reference=dense,policy_requests=sum(p['requests'] for p in policies.values()),policy_outcomes=total,
        independent_output_audit={k:v for k,v in independent.items() if k!='cases'},
        source_audit={name:{'counts':r['counts'],'substantive':r['substantive']} for name,r in source_audit['repositories'].items()},
        remaining_gaps=['Matched dense/PD/MoE/joint request E2E references are still required for the original overall accuracy gate.',
          'Public rank-0 GPU traces do not establish full RDMA latency, physical topology, request E2E or hotspot-routing accuracy.'],
        natural_person_signoff='not_required_by_user_for_this_closeout',
        prior_attempts=attempts,
        hardware_validation='excluded_from_this_closeout')
    save(doc/'acceptance-report.json',consolidation)
    save(doc/'reproduction-confirmation.json',replay)
    save(doc/'environment.json',dict(windows=before,linux=linux['environment'],native_build=read(environment/'environment-report.json')))
    save(doc/'reference-inventory.json',dict(deepseek_source=read(ROOT/'configs/dag/finalize/deepseek-source.json'),analysis=traces,
        dense_reference_kind='fresh_ns3_with_previously_frozen_calibration',controlled_reference_kind='synthetic_component_harness',official_request_e2e=report['full_scope_accuracy']))
    with (out/'scale-overhead.csv').open(encoding='utf-8') as f:scales=list(csv.DictReader(f))
    scale_table='\n'.join(f"| {r['request_count']} | {r['task_count']} | {r['event_count']} | {float(r['wall_time_s']):.2f} | {int(r['peak_rss_bytes'])/1024**2:.2f} | {r['event_queue_peak']} |" for r in scales)
    text=f'''# 跨阶段最终收尾

本目录与 phase1–phase8 并列，负责修复、补证、复现和最终交付。历史阶段记录不迁移、不改写。

本轮分支 **{consolidation['branch']}**，基线提交 `{consolidation['base_commit']}`。被测实现还包含未提交改动，精确身份由工作区差异、源码 SHA-256 和 runtime-source.zip 固定，不能把基线 HEAD 单独当作完整被测版本。

首轮长路径完整回归为373通过、1个新路径校验兼容性失败；第二轮374通过且dense实验通过，但编排器误用旧函数返回码而中止。临时根隔离与返回值适配修正后，本轮完整复跑通过。原失败、原源码快照与原始 XML 均保存在 prior-attempts/，以短序号保存并另列原 run_id，不删除失败样本或改写历史记录。

**工程收尾与 Codex 自动化复现确认通过；完整四场景 E2E 精度仍待补证，整体 pending。** 本轮未开展新的 GPU 实测，用户不要求额外自然人签字。此政策仅适用于本轮，不改写历史签字记录。

| 项目 | 结果 |
|---|---|
| Windows 长输出目录完整回归 | {report['regression']['tests']} passed，0 failed；pytest 临时目录改为短且独占的项目缓存路径 |
| Linux 本地干净检出完整回归 | exit 0，原始 XML 与日志保留 |
| 原 CLI 联合执行、背压、三档规模 | passed；唯一完成、KVReady、最终费用、资源释放均检查 |
| 独立 CPU 机制参考 | 24场景 passed；合成组件级一致性，不冒充完整请求精度 |
| 已有策略对照复跑 | {sum(p['requests'] for p in policies.values())} 次请求评估；{total['improved']} 改善、{total['tied']} 持平、{total['regressed']} 退化 |
| 新通信后端与冻结 dense 校准 | E2E 平均相对误差 {dense['old_mean_relative_error']:.4%} → {dense['revised_mean_relative_error']:.4%}；本轮未重新拟合 |
| DeepSeek 原始 trace | prefill/decode 固定提交与原始 SHA；仅行为参考，缺少匹配独立预测和完整身份，不计算虚构精度 |
| ns-3 工作树差异 | 批量 Git blob 比较完成；原始字节、换行和模式差异分别记录，子模块无未解释实质差异 |
| Codex 独立环境复现确认 | passed；Windows/Linux 关键数量及时间、24场景、dense 与 trace 解析核对 |
| 独立输出审计 | {independent['cli_outputs']} 输出、{independent['graphs']} 图、{independent['tasks']} 任务 passed |
| 原计划四场景请求 E2E | {report['full_scope_accuracy']}；不能用局部指标或合成参考替代 |

DeepSeek 原件显示 H800、rank 0，prefill world_size/EP32、decode EP128。当前文件的 kernel 时间字段为整数；解析器保留小数精度的能力由测试覆盖，不声称本轮原件出现了小数截断改善。不能从单 rank GPU kernel 推断整个 RDMA 完成或请求到达/完成边界。

三档开销在其他实验之前单独测量；后续策略实验并发，其墙钟不作为孤立性能基线。

| 请求数 | 任务数 | 宿主事件 | 墙钟/s | RSS峰值/MiB | 队列峰值 |
|---:|---:|---:|---:|---:|---:|
{scale_table}

## 入口与证据

统一入口：`python scripts/dag_finalize/main.py --output results/dag/finalize/<run_id> --environment-evidence <环境证据目录> --reference-data <固定DeepSeek原件目录>`。
run_id 为 `YYYYMMDD-finalize-purpose-NN`，拒绝覆盖。`--pytest-basetemp` 可选，必须是项目 `.cache` 下不存在的目录；默认 `.cache/p8t/`，不删除调用者已有目录，不修改 Windows 全局配置。

首次环境准备使用 linux_environment.py，在 WSL Linux 本地磁盘固定源码与子模块，独立安装 CPython 3.12.10、两个 venv 并构建后端。DeepSeek 用 deepseek.py 按 configs/dag/finalize/deepseek-source.json 固定提交获取。完整实际 argv、环境版本、构建日志和哈希都在证据包。

主入口默认运行全部工作；`--replay` 仅供 bridge 执行 Linux 主要结果重放，其前置完整回归由 bridge 单独记录。运行前冻结源文件，运行结束再次核验；执行过程中不可编辑被测代码或配置。

退出码：1=运行/功能失败或无效输入；2=功能完成但必需精度参考/复现门槛未齐；0=声明门槛全部满足。本轮正式入口返回 **{report['exit_code']}**，不把组件通过升级为项目精度通过。

- [结构化报告](acceptance-report.json)、[环境](environment.json)、[参考准入清单](reference-inventory.json)、[自动化复现确认](reproduction-confirmation.json)。
- [剩余缺口与关闭条件](remaining-gaps.md)。
- [正式证据包](artifacts/{out.name}.zip) 和 [SHA256SUMS](artifacts/SHA256SUMS)。
- 原始运行：`results/dag/finalize/{out.name}/`，受 Git 忽略。ZIP 包含原件、命令、日志、XML、冻结费用、源码快照和时间线，排除 venv、预测缓存及 pytest 临时目录。

本轮不自动提交、合并或推送。受控路径修复兼容旧 phase8 入口；旧文档、历史结果和 ZIP 保持原样。
'''
    (doc/'README.md').write_text(text,encoding='utf-8',newline='\n')
    (doc/'remaining-gaps.md').write_text('''# 剩余缺口

1. 正式四场景 request_e2e 配对仍为空。需要相同模型、设备、输入、并行配置、拓扑、dtype 和指标定义的参考/旧预测/新预测，并按组隔离校准与验证。数据不齐保持 blocked。
2. DeepSeek 是单 rank、均衡路由 profiling；H800 与 EP 信息可恢复，但不能补造请求边界、全部 rank、网络拓扑或 source→destination 路由。现有数据仅行为参考，没有把 trace 自身用作费用再冒充独立预测。
3. 独立 CPU 参考是受控 Executor+KV API 组件检查，不导入 DAG 执行器来生成参考，不验证真实算子费用。实际宿主链路由原 CLI 联合运行和完整回归另行覆盖。
4. submission 默认保持兼容；FCFS 的误差改善针对匹配的端点排队假设。未证明任意拓扑、任意多资源仲裁均符合该参考。
5. 真实硬件验证按用户要求排除；本轮 Codex 自动化复现确认已经完成，不再要求额外自然人签字。历史签字状态不被追溯更改。

关闭原计划精度缺口必须补齐合格数据并通过原主指标，不能缩小场景、替换指标或删除退化样本。没有新增硬件数据时，只能声称相对已声明模拟参考模型的改善。
''',encoding='utf-8',newline='\n')
    delivery=out/'final-delivery';delivery.mkdir(exist_ok=False)
    for path in doc.iterdir():
        if path.is_file():shutil.copyfile(path,delivery/path.name)
    files=[p for p in out.rglob('*') if p.is_file() and not excluded(p.relative_to(out)) and p.name!='delivery-manifest.json']
    manifest=dict(run_id=out.name,base_commit=consolidation['base_commit'],artifact_sha256={p.relative_to(out).as_posix():digest(p) for p in sorted(files)})
    save(out/'delivery-manifest.json',manifest);files.append(out/'delivery-manifest.json')
    artifacts=doc/'artifacts';artifacts.mkdir(exist_ok=True);archive=artifacts/(out.name+'.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(files):z.write(path,out.name+'/'+path.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('archive CRC failed')
        from hashlib import sha256
        for name,h in manifest['artifact_sha256'].items():
            if sha256(z.read(out.name+'/'+name)).hexdigest()!=h:raise ValueError('archive hash mismatch: '+name)
    (artifacts/'SHA256SUMS').write_text(digest(archive)+'  '+archive.name+'\n',encoding='utf-8',newline='\n')
    # Check Git's prospective cleaned blob without adding or writing any object/index.
    checks={}
    for path in doc.rglob('*'):
        if not path.is_file():continue
        payload=path.read_bytes();raw=sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
        clean=subprocess.check_output(['git','hash-object','--stdin','--path',path.relative_to(ROOT).as_posix()],input=payload,cwd=ROOT).decode().strip()
        if raw!=clean:raise ValueError('Git would change published bytes: '+str(path))
        checks[path.relative_to(ROOT).as_posix()]=dict(sha256=digest(path),prospective_git_blob_matches_raw=True)
    save(out/'published-byte-verification.json',checks)
    print(json.dumps(dict(archive=str(archive),bytes=archive.stat().st_size,files=len(files),status='engineering_passed_e2e_blocked')))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--environment-evidence',type=Path,required=True);p.add_argument('--prior-attempt',type=Path,action='append',default=[]);a=p.parse_args()
    publish(a.run,a.environment_evidence,a.prior_attempt)
