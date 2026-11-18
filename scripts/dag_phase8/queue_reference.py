"""Standalone FCFS reference. No SimAI, DAG, scheduler, or timeline imports.

For one request per two-stage replica, the only shared resource is the PP
endpoint. A job reaches it after stage-0 work preceding the transfer. The server
is nonpreemptive and FCFS by arrival, then request index. Costs are fixed inputs.
"""
import argparse
from decimal import Decimal, localcontext
import json
from pathlib import Path


def decimal(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("reference requires finite nonnegative times")
    return result


def predict(case, contract, policy="fcfs"):
    if case["endpoint"] not in ("shared", "private"):
        raise ValueError("unknown endpoint policy")
    if policy not in ("fcfs", "submission_priority"):
        raise ValueError("unknown queue policy")
    jobs = []
    with localcontext() as context:
        context.prec = 40
        for index, tokens in enumerate(case["tokens"]):
            stages = contract["tokens"][str(tokens)]
            before, after = stages["0"], stages["1"]
            transfer = decimal(before["components_ms"]["pipeline_parallel_communication_time"]) / 1000
            cpu_post = sum((decimal(before["components_ms"][name]) for name in
                            ("sampler_e2e_time", "process_model_outputs_time", "ray_comm_time")), Decimal(0)) / 1000
            arrival = decimal(case["arrivals_s"][index]) if "arrivals_s" in case else decimal(case["arrival_gap_s"]) * index
            preceding = decimal(before["total_s"]) - transfer - cpu_post
            if preceding < 0 or decimal(after["components_ms"]["pipeline_parallel_communication_time"]) != 0:
                raise ValueError("invalid two-stage service contract")
            jobs.append(dict(request_id=index, prefill_tokens=tokens, arrival=arrival,
                ready=arrival + preceding, transfer=transfer,
                trailing=cpu_post + decimal(after["total_s"]),
                endpoint="fabric" if case["endpoint"] == "shared" else f"nic:{index}"))
        rows = []
        for endpoint in sorted({job["endpoint"] for job in jobs}):
            remaining = [job for job in jobs if job["endpoint"] == endpoint]
            clock = Decimal(0)
            while remaining:
                clock = max(clock, min(job["ready"] for job in remaining))
                eligible = [job for job in remaining if job["ready"] <= clock]
                job = min(eligible, key=(lambda item: (item["ready"], item["request_id"]))
                          if policy == "fcfs" else (lambda item: item["request_id"]))
                start = clock
                end = start + job["transfer"]
                clock = end
                remaining.remove(job)
                complete = end + job["trailing"]
                rows.append(dict(request_id=job["request_id"], prefill_tokens=job["prefill_tokens"], endpoint=job["endpoint"],
                    arrived_at_s=float(job["arrival"]), communication_ready_s=float(job["ready"]),
                    communication_start_s=float(start), communication_end_s=float(end),
                    communication_service_s=float(job["transfer"]), resource_wait_s=float(start-job["ready"]),
                    completed_at_s=float(complete), request_e2e_s=float(complete-job["arrival"])))
    return sorted(rows, key=lambda row: row["request_id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--cost-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", choices=("fcfs", "submission_priority"), default="fcfs")
    args = parser.parse_args()
    result = predict(json.loads(args.case.read_text()), json.loads(args.cost_contract.read_text()), args.policy)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(dict(reference_type="independent_decimal_queue", queue_policy=args.policy, hardware_accuracy_claim=False, requests=result),
                  stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
