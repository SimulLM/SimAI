import atexit
import heapq
import json
import math
from pathlib import Path
from typing import List

from vidur.config import SimulationConfig
from vidur.entities import Cluster
from vidur.events import BaseEvent, RequestArrivalEvent
from vidur.logger import init_logger
from vidur.metrics import MetricsStore
from vidur.request_generator import RequestGeneratorRegistry
from vidur.scheduler import BaseGlobalScheduler, GlobalSchedulerRegistry

logger = init_logger(__name__)


class Simulator:
    def __init__(self, config: SimulationConfig) -> None:
        self._config: SimulationConfig = config

        self._time = 0
        self._terminate = False
        self._time_limit = self._config.time_limit
        if not self._time_limit:
            self._time_limit = float("inf")

        # 最小堆，(优先级，事件)
        # 优先级为(self._time, self._id, self.event_type)
        # 因此event会按照时间排序
        
        # Min heap, (priority, event)
        # Priority is (self._time, self._id, self.event_type)
        # Therefore events will be sorted by time
        self._event_queue = []

        self._event_trace = []
        self._event_chrome_trace = []

        self._cluster = Cluster(
            self._config.cluster_config,
            self._config.metrics_config,
            self._config.request_generator_config,
        )
        self._metric_store = MetricsStore(self._config)
        self._request_generator = RequestGeneratorRegistry.get(
            self._config.request_generator_config.get_type(),
            self._config.request_generator_config,
        )

        self._scheduler = GlobalSchedulerRegistry.get(
            self._config.cluster_config.global_scheduler_config.get_type(),
            self._config,
            self._cluster.replicas,
        )

        self._scheduler.stage_execution_records = []
        self._scheduler.dag_adapter = None
        self._failure = None
        if config.execution_mode == "dag_coarse":
            from vidur.dag.host import CoarseDagAdapter
            self._scheduler.dag_adapter = CoarseDagAdapter(
                (replica_id, stage_id)
                for replica_id, replica in self._scheduler._replica_schedulers.items()
                for stage_id in replica._replica_stage_schedulers
            )

        self._init_event_queue()
        atexit.register(self._write_output)

    @property
    def scheduler(self) -> BaseGlobalScheduler:
        return self._scheduler

    @property
    def metric_store(self) -> MetricsStore:
        return self._metric_store

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:
            self._failure = f"{type(exc).__name__}: {exc}"
            raise

    def _run(self) -> None:
        logger.info(
            f"Starting simulation with cluster: {self._cluster} and {len(self._event_queue)} requests"
        )

        # 判断event；
        # Process events
        
        tmp_pre_debug_time = 0
        while self._event_queue and not self._terminate:
            
            # 弹出优先级最高的事件
            # Pop the highest priority event
            _, event = heapq.heappop(self._event_queue)
            # 设置系统时间为事件发生的时间
            # Set system time to the event occurrence time
            self._set_time(event._time)
            if tmp_pre_debug_time == 0 and event._time > tmp_pre_debug_time:
                tmp_pre_debug_time = event._time
            elif tmp_pre_debug_time > 0 and tmp_pre_debug_time > event._time:
                assert tmp_pre_debug_time <= event._time, (
                    f"Event time went backwards: prev={tmp_pre_debug_time} cur={event._time}"
                )
                
            assert event._time >= 0, "Event time must be non-negative"
            logger.debug(f"len(_event_queue){len(self._event_queue)}, event_type={event._event_type}, time={event._time}")
            
            # 处理事件，事件可能会触发新的事件
            # Handle the event, events may trigger new events
            new_events = event.handle_event(self._scheduler, self._metric_store)
            self._add_events(new_events)

            adapter = self._scheduler.dag_adapter
            if adapter is not None:
                adapter.now = self._time
                adapter.pending_event_count = len(self._event_queue)
                adapter.queue_peak = max(adapter.queue_peak, len(self._event_queue))

            if self._config.metrics_config.write_json_trace:
                self._event_trace.append(event.to_dict())

            if self._config.metrics_config.enable_chrome_trace:
                chrome_trace = event.to_chrome_trace()
                if chrome_trace:
                    self._event_chrome_trace.append(chrome_trace)

        # print(f"> Debug: self._scheduler.is_empty()={self._scheduler.is_empty()} self._terminate={self._terminate}")
        assert self._scheduler.is_empty() or self._terminate
        if not self._terminate and any(not request.completed for request in self._requests):
            raise RuntimeError("host queue exhausted with unfinished requests")

        if self._scheduler.dag_adapter is not None and not self._terminate:
            self._scheduler.dag_adapter.assert_completed()

        logger.info(f"Simulation ended at: {self._time}s")
        
        # [AICB优化] 模拟结束时打印缓存统计并保存查表
        try:
            from vidur.entities.execution_time import _GLOBAL_AICB_CACHE
            _GLOBAL_AICB_CACHE.print_stats()
            _GLOBAL_AICB_CACHE.save_lookup_table()
        except Exception as e:
            logger.warning(f"Cannot print AICB cache stats (无法打印AICB缓存统计): {e}")

    def _write_output(self) -> None:
        logger.info("Writing output")

        output = Path(self._config.metrics_config.output_dir)
        with (output / "execution-summary.json").open("w", encoding="utf-8") as stream:
            json.dump({"execution_mode": self._config.execution_mode,
                       "status": "failed" if self._failure else ("truncated" if self._terminate else "completed"),
                       "error": self._failure, "final_time_s": self._time,
                       "requests": [request.to_dict() for request in self._requests],
                       "stages": self._scheduler.stage_execution_records}, stream, indent=2, allow_nan=False)
        if self._scheduler.dag_adapter is not None:
            from vidur.dag.trace import write_results
            adapter = self._scheduler.dag_adapter
            adapter.now = self._time
            adapter.pending_event_count = len(self._event_queue)
            write_results(output, adapter, error=self._failure or ("time limit reached" if self._terminate else None))

        self._metric_store.plot()
        logger.info("Metrics written")

        if self._config.metrics_config.write_json_trace:
            self._write_event_trace()
            logger.info("Json event trace written")

        if self._config.metrics_config.enable_chrome_trace:
            self._write_chrome_trace()
            logger.info("Chrome event trace written")

    def write_output(self) -> None:
        # Original CLI must propagate output failures instead of hiding them in atexit.
        atexit.unregister(self._write_output)
        self._write_output()

    def _add_event(self, event: BaseEvent) -> None:
        if not math.isfinite(event.time) or event.time < self._time:
            raise ValueError("event must have finite time at or after Simulator time")
        # 将事件按照优先级加入队列
        # Add event to queue according to priority
        heapq.heappush(self._event_queue, (event._priority_number, event))

    def _add_events(self, events: List[BaseEvent]) -> None:
        for event in events:
            self._add_event(event)

    def _init_event_queue(self) -> None:
        requests = self._request_generator.generate()
        self._requests = requests

        # 生成请求，把请求加入到时间队列中
        # Generate requests and add them to the time queue
        for request in requests:
            logger.debug(f"arrived_at={request.arrived_at} RequestArrivalEvent generated, request_id={request._id}")
            self._add_event(RequestArrivalEvent(request.arrived_at, request))

    def _set_time(self, time: float) -> None:
        self._time = time
        if self._time > self._time_limit:
            logger.info(
                f"Time limit reached: {self._time_limit}s terminating the simulation."
            )
            self._terminate = True

    def _write_event_trace(self) -> None:
        def encode_collection(value):
            if isinstance(value, set):
                return sorted(value)
            raise TypeError(f"unsupported trace value: {type(value).__name__}")

        trace_file = f"{self._config.metrics_config.output_dir}/event_trace.json"
        with open(trace_file, "w") as f:
            json.dump(self._event_trace, f, default=encode_collection)

    def _write_chrome_trace(self) -> None:
        trace_file = f"{self._config.metrics_config.output_dir}/chrome_trace.json"

        chrome_trace = {"traceEvents": self._event_chrome_trace}

        with open(trace_file, "w") as f:
            json.dump(chrome_trace, f)
