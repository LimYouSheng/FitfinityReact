"""Group reviewed release steps without replaying uncertain provider writes."""

import time
from copy import deepcopy

from operator_checks import require


class Milestone:
    """Retain each canonical receipt and poll only read-only transitions."""

    def __init__(self, step, persist, *, clock=time.time, pause=time.sleep, budget=1500):
        self.step = step
        self.persist = persist
        self.clock = clock
        self.pause = pause
        self.deadline = clock() + budget

    def run(self, mode, prior=None):
        """Persist the active phase alongside original intent before every effect."""
        require(self.clock() < self.deadline, "Milestone deadline reached; inspect original intent")

        retained = None

        def save(receipt):
            nonlocal retained
            value = {**deepcopy(receipt), "milestone_phase": mode}
            self.persist(value)
            retained = deepcopy(value)

        self.step(mode, prior, save)
        require(retained is not None, "Step did not retain a durable receipt")
        return retained

    def wait(self, mode, prior, ready):
        """Wait for an observed state without repeating mutation requests."""
        while True:
            prior = self.run(mode, prior)
            if ready(prior):
                return prior
            self.delay(10)

    def delay(self, seconds):
        """Bound a provider-state or drain wait by the milestone deadline."""
        remaining = self.deadline - self.clock()
        require(remaining > 0, "Milestone deadline reached; inspect original intent")
        self.pause(min(seconds, remaining))


def change_set_ready(receipt):
    """Reject terminal change-set failures before attempting execution."""
    status = receipt.get("change_set_status")
    require(
        status in {"CREATE_PENDING", "CREATE_IN_PROGRESS", "CREATE_COMPLETE"},
        "Change set failed; inspect original intent",
    )
    require(not receipt.get("execution_requested"), "Execution already requested; do not replay")
    return status == "CREATE_COMPLETE" and receipt.get("execution_status") == "AVAILABLE"


def stack_complete(receipt):
    """Stop on rollback or deletion instead of repeatedly waiting for success."""
    status = receipt.get("stack_status")
    require(receipt.get("execution_requested") is True, "Original execution intent required")
    require(
        status
        in {
            "CREATE_COMPLETE",
            "UPDATE_IN_PROGRESS",
            "UPDATE_COMPLETE_CLEANUP_IN_PROGRESS",
            "UPDATE_COMPLETE",
        },
        "Stack update failed; inspect original intent",
    )
    require(
        receipt.get("execution_status") in {"AVAILABLE", "EXECUTE_IN_PROGRESS", "EXECUTE_COMPLETE"},
        "Change-set execution failed; inspect original intent",
    )
    return status == "UPDATE_COMPLETE" and receipt.get("execution_status") == "EXECUTE_COMPLETE"


def maintenance_backup(review, call, persist, *, profile, prior=None, clock=None, pause=time.sleep):
    """Pause or adopt, record the pause and verify one backup under one approval."""
    from release_maintenance import execute

    live_clock = clock is None
    clock = time.time if live_clock else clock

    def step(mode, previous, save):
        return execute(
            mode,
            review,
            call,
            save,
            profile=profile,
            prior=previous,
            now=None if live_clock else clock(),
        )

    runner = Milestone(step, persist, clock=clock, pause=pause)
    receipt = runner.run("adopt-pause" if "prior_identity" in review else "pause", prior)
    receipt = runner.run("inspect", receipt)
    require(receipt.get("state") == "paused", "Pause was not observed")
    while clock() < receipt["drained_after"]:
        runner.delay(receipt["drained_after"] - clock())
    if "prior_pause_record_sha256" not in review:
        receipt = runner.run("record-pause-create", receipt)
        receipt = runner.wait(
            "record-pause-inspect", receipt, lambda row: change_set_ready(row["pause_record"])
        )
        receipt = runner.run("record-pause-execute", receipt)
        receipt = runner.wait(
            "record-pause-inspect", receipt, lambda row: stack_complete(row["pause_record"])
        )
        receipt = runner.run("record-pause-verify", receipt)
    receipt = runner.run("snapshot", receipt)
    return runner.wait("snapshot-check", receipt, lambda row: row.get("state") == "snapshot_ready")


def rollout_milestone(mode, step, persist, *, clock=time.time, pause=time.sleep):
    """Deploy paused artifacts or explicitly resume through existing guarded steps."""
    require(mode in {"deploy", "resume"}, "Unknown rollout milestone")
    runner = Milestone(step, persist, clock=clock, pause=pause)
    prefix = "resume-" if mode == "resume" else ""
    if mode == "deploy":
        uploaded = runner.run("upload")
        runner.run("upload-inspect", uploaded)
    receipt = runner.run(prefix + "create")
    receipt = runner.wait(prefix + "inspect", receipt, change_set_ready)
    receipt = runner.run(prefix + "execute", receipt)
    receipt = runner.wait(prefix + "inspect", receipt, stack_complete)
    receipt = runner.run(prefix + "verify", receipt)
    if mode == "resume":
        receipt = runner.run("resume-health", receipt)
        receipt = runner.run("resume-finalize", receipt)
        receipt = runner.run("resume-finalize-inspect", receipt)
        require(receipt.get("state") == "maintenance_finalized", "Finalization was not observed")
    return receipt
