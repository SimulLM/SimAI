# F：验收、输出与交接

入口为 `scripts/dag_phase6/main.py`。使用阶段4推理依赖，安装到项目虚拟环境；当前使用Python 3.15.2。PyYAML在本机以PYYAML_FORCE_LIBYAML=0构建纯Python版本，未安装系统编译器。

完整验收从项目根目录运行：

```powershell
$env:TEMP = (Resolve-Path .cache/dag-phase1-install-tmp).Path
$env:TMP = $env:TEMP
& ./.cache/dag-phase1-py315/Scripts/python.exe scripts/dag_phase6/main.py --output results/dag/phase6/<new_run_id>
```

脚本执行五组原CLI场景，再运行阶段1—5/7和阶段6测试，保存pytest.log/xml。`--skip-tests`仅用于开发时运行CLI探针，报告注明未运行完整回归。输出目录必须不存在。

退出码0保留给功能及精度通过；1表示功能或运行失败；当前缺匹配PD参考，功能通过时退出2。accuracy_status固定明确记录blocked_missing_matched_pd_reference，不用合成功能数据计算硬件误差。

输出包括原任务/资源时间线、cost-breakdown、全部图和Chrome trace；新增pd-summary.json、pd-transfers.csv、kv-events.json、kv-capacity.csv，记录存储与传输bytes、容量等待、资源等待工作量、实际传输起止、KVReady、首次Decode和清理状态。network_resource_wait_work_s是各任务等待之和，可能重叠，不等于请求新增时延。

run-manifest保存命令、Python/依赖、Git HEAD/status/diff、源码与产物哈希、墙钟和合成数据属性。产物哈希排除pytest临时文件和预测器缓存。阶段5的TP校准不用于PD链路；PD参数由配置单独给定。

精度后续需要相同模型、设备、TP/PP、KV布局/dtype、请求输入和拓扑的独立PD参考；分别比较旧预测、同费用DAG和修订费用DAG，划分calibration/validation。当前交付只验功能，保留该证据缺口。

早期环境准备时的基线收集因依赖未安装完成而失败，首次联合回归还发现一个新增异常处理边界及验收环境PYTHONPATH/运行中源码变化问题。日志保留在results/dag/phase6；不能将这些开发运行当作正式通过。最终验收使用固定源码和完整环境，结果以对应acceptance-report、JUnit及manifest为准。
