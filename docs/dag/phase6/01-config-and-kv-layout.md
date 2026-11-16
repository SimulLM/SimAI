# A：配置与KV布局

已实现严格PD配置和同构分片布局。`pd.py`读取v1配置，`kv_layout.py`计算每分片存储与传输字节。

配置显式给出storage_dtype、capacity_bytes_per_shard、bandwidth_bytes_per_s、latency_s、occupies_gpu、evidence及schema_version。未知字段、非法单位数值、缺失证据均拒绝。wire dtype与storage dtype相同。

每分片每Token字节数为2×每Stage层数×每rank KV heads×head_dim×dtype字节。KV heads足够时均匀分片；TP大于KV heads时按rank复制，要求整除。层数须整除PP。存储按块向上对齐，wire只包含有效Token，不传预分配空块。

首轮有效KV Token取Prefill输入Token数；原请求额外计入的首个输出Token尚未经过下一轮前向，不能计为已有KV。

验证命令：项目环境运行 `python -m pytest tests/dag/test_pd_layout.py -q`，15项通过。覆盖MHA/GQA/MQA分片或复制、块对齐、非法配置和未知字段。后续模块复用该布局，不重新估算字节。
