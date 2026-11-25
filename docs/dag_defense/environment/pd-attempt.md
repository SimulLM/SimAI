# PD setup checkpoint

The first real 1P1D service launch on the new dual-H800 host failed before inference. Both vLLM 0.8.5 instances failed tokenizer initialization because transformers 5.24.1 removed all_special_tokens_extended. Logs are retained on the server under /root/autodl-tmp/dag-handoff/runs/smoke-failed-transformers5/. The isolated environment was then pinned to transformers 4.51.3, tokenizers 0.21.1, and huggingface-hub 0.34.6; pip check passed. A new attempt is underway. No smoke request or formal experiment has completed at this checkpoint.

The selected model is NousResearch/Llama-2-7b-hf at revision 8efe6c9b93655b934e27bd9981e3ec13e55aee9d. Its uploaded files passed SHA256 on this host. GPU UUIDs and topology are in hardware-check.txt. Baseline checkout is at cef83f9ddd96540e3e9f48934f11335d52d54fce; the original dev-finalize worktree is preserved.

## Two-instance diagnostic request

With transformers 4.51.3 the GPU0 producer and GPU1 consumer started using PyNcclConnector, FP16, TP1, prefix and chunked prefill disabled. A diagnostic request returned HTTP 200 with 6 input and 8 output tokens; response is smoke-response.txt. The prefill and decode logs use different request IDs and the sample proxy maps neither ID, so trace completeness is not established. The connector may fall back to model forwarding if KV is missing; explicit KVReady, transfer completion and actual NCCL path were not recorded. Therefore the PD smoke gate remains blocked pending instrumented evidence. Earlier proxy returned 400 because prefill max_tokens=1 conflicted with min_tokens=8; it incorrectly continued to decode and the request timed out. The diagnostic proxy was adjusted to set prefill min_tokens=0. A proxy port conflict was also observed; launch script requires robust lifecycle fixes before use.

## Connector debug diagnostic

A separate diagnostic run with VLLM_LOGGING_LEVEL=DEBUG returned eight tokens and logged `KV send DONE` on the producer and `Successfully received all KVs and hidden states, skip model forwarding` on the consumer. See diagnostics/kv-debug-excerpts.txt and response. This supports KV handoff, but does not provide a mapped request ID, GPU completion timestamps, actual NCCL transport path, payload records, or the full plan-required events. It is not a validated timing dataset.
