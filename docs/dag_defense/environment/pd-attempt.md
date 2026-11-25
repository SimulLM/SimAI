# PD setup checkpoint

The first real 1P1D service launch on the new dual-H800 host failed before inference. Both vLLM 0.8.5 instances failed tokenizer initialization because transformers 5.24.1 removed all_special_tokens_extended. Logs are retained on the server under /root/autodl-tmp/dag-handoff/runs/smoke-failed-transformers5/. The isolated environment was then pinned to transformers 4.51.3, tokenizers 0.21.1, and huggingface-hub 0.34.6; pip check passed. A new attempt is underway. No smoke request or formal experiment has completed at this checkpoint.

The selected model is NousResearch/Llama-2-7b-hf at revision 8efe6c9b93655b934e27bd9981e3ec13e55aee9d. Its uploaded files passed SHA256 on this host. GPU UUIDs and topology are in hardware-check.txt. Baseline checkout is at cef83f9ddd96540e3e9f48934f11335d52d54fce; the original dev-finalize worktree is preserved.
