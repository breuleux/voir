import time


class DataloaderWrapper:
    """Time the body of a loop, ignoring the time it took to initialize the iterator.
    The timings are measured using `torch.cuda.Event` to avoid explicit sync.

    An explicit sync is done at the end of an epoch or if the max number of observation is reached.

    Because the timings are async, voir only gets triggered when the explicit sync happen which
    is outside of the scope of performance measure, so no matter how long voir takes to process
    the events it will not impact the measures
    
    Examples
    --------

    .. code-block::

       loader = DataloaderWrapper(loader, torch.cuda.Event, earlystop=60)   # < here

       for e in range(epochs):
           for i in loader:
               loss = criterion(model(x), y)

               loader.add_loss(loss)                                        # < here
    """
    def __init__(self, loader, event_fn, earlystop=None):
        self.loader = loader
        self.events = []
        self.losses = []
        self.total_obs = 0
        self.event_fn = event_fn
        self.world_size = 1
        self.early_stop = earlystop
        self.loader_init_time = []

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
        for i in iterator:
            yield i

            end = self.event_fn(enable_timing=True)
            end.record()
            bs = self.deduce_batch_size(i)
            self.events.append((start, end, bs))

            # check for early stopping to avoid doing the full epoch
            self.earlystop()
            start = end

        self._push()

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

    def _push(self):
        # Push synchronize to have the final compute times
        for start, end, bs in self.events:
            end.synchronize()
            elapsed = start.elapsed_time(end) / 1000
            rate = (bs * self.world_size) / elapsed
            self.log_rate(rate)

        for loss in self.losses:
            self.log_loss(loss.item())

        self.total_obs += len(self.events)
        self.events = []
        self.losses = []
    
    def add_loss(self, loss):
        # avoid .item() that cause sync
        self.losses.append(loss.detach())

    def log_rate(self, rate):
        print("rate", rate)
    
    def log_loss(self, loss):
        print("loss", loss)



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
