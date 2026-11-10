from typing import List

from schemas.dag.v1.io import finite_nonnegative

from vidur.events import BaseEvent
from vidur.logger import init_logger
from vidur.metrics import MetricsStore
from vidur.scheduler import BaseGlobalScheduler
from vidur.types import EventType

logger = init_logger(__name__)


class ReplicaStageScheduleEvent(BaseEvent):
    def __init__(self, time: float, replica_id: int, stage_id: int):
        super().__init__(time, EventType.REPLICA_STAGE_SCHEDULE)

        self._replica_id = replica_id
        self._stage_id = stage_id

        self._batch = None
        self._batch_stage = None
        self._is_last_stage = None

    def handle_event(
        self, scheduler: BaseGlobalScheduler, metrics_store: MetricsStore
    ) -> List[BaseEvent]:
        from vidur.events.batch_stage_end_event import BatchStageEndEvent

        stage_scheduler = scheduler._replica_schedulers[
            self._replica_id
        ]._replica_stage_schedulers[self._stage_id]

        # PP stage执行一个micro-batch
        # PP stage executes a micro-batch   
        self._batch, self._batch_stage, execution_time = stage_scheduler.on_schedule()

        if not (self._batch and self._batch_stage):
            return []

        # Validate before metrics or business state consume predictor output. Keep
        # rejected input explicitly diagnostic, never in the numeric cost field.
        records = getattr(scheduler, "stage_execution_records", None)
        record = {"batch_stage_id": self._batch_stage.id,
                  "batch_id": self._batch.id, "replica_id": self._replica_id,
                  "stage_id": self._stage_id, "request_ids": self._batch.request_ids,
                  "num_tokens": list(self._batch.num_tokens), "submitted_at_s": self.time,
                  "start_at_s": None, "resource_wait_s": None,
                  "predicted_duration_s": None, "end_at_s": None, "completion_count": 0}
        try:
            finite_nonnegative(self._batch_stage.execution_time)
        except ValueError as exc:
            record.update(invalid_predicted_duration=repr(self._batch_stage.execution_time),
                          validation_error=str(exc))
            if records is not None:
                records.append(record)
            raise ValueError(f"invalid Stage execution time: {exc}") from exc
        record["predicted_duration_s"] = self._batch_stage.execution_time
        if records is not None:
            records.append(record)

        def on_stage_start(start_at):
            self._batch_stage.on_schedule(start_at, submitted_at=self.time)
            record.update(start_at_s=start_at, resource_wait_s=start_at - self.time)
            metrics_store.on_replica_stage_schedule(
                start_at, self._replica_id, self._stage_id, self._batch_stage, execution_time)

        self._is_last_stage = stage_scheduler.is_last_stage

        adapter = getattr(scheduler, "dag_adapter", None)
        if adapter is not None:
            return adapter.submit_stage(self.time, self._replica_id, self._stage_id,
                                        self._is_last_stage, self._batch, self._batch_stage,
                                        on_stage_start=on_stage_start)

        on_stage_start(self.time)

        logger.debug(f"time={self._time} Event {self._id} of type {self._event_type} "
            f"Generates 1 BatchStageEndEvent replica_id={self._replica_id} stage_id={self._stage_id} "
            f"batch_stage={self._batch_stage}")
        assert self._batch_stage.execution_time >= 0, \
            f"batch_stage execution_time must be non-negative, got {self._batch_stage.execution_time}"
        
        return [
            BatchStageEndEvent(
                # 执行micro-batch消耗时间
                # Execution time for the micro-batch
                self.time + self._batch_stage.execution_time,
                self._replica_id,
                self._stage_id,
                self._is_last_stage,
                self._batch,
                self._batch_stage,
            ),
        ]

    def to_dict(self):
        return {
            "time": self.time,
            "event_type": self.event_type,
            "replica_id": self._replica_id,
            "stage_id": self._stage_id,
            "batch_id": self._batch.id if self._batch else None,
            "batch_stage_id": self._batch_stage.id if self._batch_stage else None,
            "is_last_stage": self._is_last_stage,
        }
