import json
import sys
import time

from giving import give
import torch
import torch.distributed as dist

from .phase import StopProgram
from .helpers import current_overseer
from .smuggle import SmuggleWriter




class DataloaderWrapper:
    """Time the body of a loop, ignoring the time it took to initialize the iterator.`
    The timings are measured using `torch.cuda.Event` to avoid explicit sync.

    An explicit sync is done at the end of an epoch or if the max number of observation is reached.

    Because the timings are async, voir only gets triggered when the explicit sync happens which
    is outside of the scope of performance measure, so no matter how long voir takes to process
    the events it will not impact the measures.

    Notes
    -----
    The event progress is the only one that is feed synchronously so
    this event should be handled quickly.
    
    Examples
    --------

    .. code-block::

       loader = DataloaderWrapper(loader, torch.cuda.Event, earlystop=60)   # < here

       for e in range(epochs):
           for i in loader:
               loss = criterion(model(x), y)

               loader.add_loss(loss)                                        # < here
    """
    def __init__(self, loader, event_fn, rank=0, device=None, earlystop=None):
        self.loader = loader
        self.events = []
        self.losses = []
        self.total_obs = 0
        self.event_fn = event_fn
        self.world_size = 1
        self.early_stop = earlystop
        self.loader_init_time = []
        self.rank = None
        self.device = device
        self.datafile = sys.stdout
        self.n = len(loader)

        if dist.is_initialized():
            self.rank = rank
            assert self.device is not None, "device is required to compute the final batch size"

    def __getattr__(self, item):
        return getattr(self.loader, item)

    def __len__(self):
        return len(loader)

    def __iter__(self):
        # This takes much more time than expected
        # good thing to keep track of it
        start = - time.time()
        iterator = iter(self.loader)
        end = time.time()

        self.loader_init_time.append(start + end)
        return self.wrapped(iterator)

    def wrapped(self, iterator):
        # Time IO wait + batch compute
        start = self.event_fn(enable_timing=True)
        start.record()

        # avoid synchronization
        for i, data in enumerate(iterator):
            yield data

            end = self.event_fn(enable_timing=True)
            end.record()
            bs = self.deduce_batch_size(data)
            self.events.append((start, end, bs))
            # check for early stopping to avoid doing the full epoch
            self.earlystop()
            start = end
            self.log_progress()

        self._push()
        self.earlystop()

    def deduce_batch_size(self, elem):
        try:
            if len(elem) == 2:
                return len(elem[0])
            return len(elem)
        except:
            return 0

    def earlystop(self):
        if self.early_stop is None:
            return 

        if len(self.events) + self.total_obs >= self.early_stop:
            self._push()
            raise StopProgram()

    def extra_work(self):
        pass

    def _push(self):
        self.extra_work()

        # Push synchronize to have the final compute times
        for start, end, bs in self.events:
            end.synchronize()
            elapsed = start.elapsed_time(end) / 1000

            # multi GPU, batch size count
            if dist.is_initialized():
                bs = torch.tensor([bs], dtype=torch.int64, device=self.device)
                dist.reduce(bs, dst=0)
                bs = bs.item()

            rate = bs / elapsed
            self.log_rate(rate)

        for loss in self.losses:
            self.log_loss(loss.item())

        self.total_obs += len(self.events)
        self.events = []
        self.losses = []
    
    def add_loss(self, loss):
        # avoid .item() that cause sync
        self.losses.append(loss.detach())
        return loss

    def log_rate(self, rate):
        if self.rank is None or self.rank == 0:
            self.message(rate=rate, units="items/s", task="train")

    def log_loss(self, loss):
        if self.rank is None or self.rank == 0:
            self.message(loss=loss, task="train")

    def log_progress(self):
        progress = len(self.events) + self.total_obs
        self.message(progress=[progress, self.early_stop])

    def message(self, **kwargs):
        kwargs.setdefault("task", "train")
        msg = json.dumps(kwargs)
        print(msg, file=self.datafile)


class DataloaderWrapperSmuggle(DataloaderWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datafile = SmuggleWriter(sys.stdout)


class DataloaderWrapperGiver(DataloaderWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ov = current_overseer.get()
    
    def log_rate(self, rate):
        if self.rank is None or self.rank == 0:
            self.ov.give(rate=rate, units="items/s", task="train")
    
    def log_loss(self, loss):
        if self.rank is None or self.rank == 0:
            self.ov.give(loss=loss, task="train")


class CPUEvent:
    def __init__(self, **kwargs):
        self.start = 0

    def record(self):
        self.start = time.time()

    def elapsed_time(self, end):
        return end.start - self.start

    def synchronize(self):
        pass


def test_():
    loader = DataloaderWrapper([([1, 2], 3) for i in range(10)], CPUEvent, 50)

    for e in range(200):
        for i in loader:
            pass
