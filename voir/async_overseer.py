
from typing import Any
from queue import Empty
import inspect
import multiprocessing
import traceback
import time
import cloudpickle
from contextlib import contextmanager

from giving import Giver
from giving.api import giver
from giving.gvr import global_context, global_inherited
from .overseer import SyncOverseer
from .phase import StopProgram, Phase, OverseerAbort


def _test_stuff(*args):
    print(args)


SHR_ON = 1

def _worker(in_queue, out_queue, shared_state, cls, cls_args):
    shared_state[SHR_ON] = 1
    
    with cls(*cls_args) as handler:
        while shared_state[SHR_ON]:
            try:
                payload = in_queue.get(True, timeout=0.01)
                funame, args, kwargs = cloudpickle.loads(payload)
                
                print("fname:", funame, args, kwargs)
                if hasattr(handler, funame):
                    r = getattr(handler, funame)(*args, **kwargs)
                    if r is not None:
                        out_queue.put(r)
                    
                if funame == "barrier":
                    out_queue.put("done")

            except Empty:
                continue
            except Exception:
                traceback.print_exc()
    

class ProcWorker:
    def __init__(self, observer_cls, observer_args=tuple(), size=20):
        self.mm = multiprocessing.Manager()
        self.in_queue = self.mm.Queue(size)
        self.out_queue = self.mm.Queue()
        self.state = self.mm.dict()
        self.worker = None
        self.observer_cls = observer_cls
        self.observer_args = observer_args
    
    def __enter__(self):
        self.mm.__enter__()
        self.state[SHR_ON] = 0
        self._init_worker()
        self._wait_worker_init()
        return self

    def _init_worker(self):
        self.worker = multiprocessing.Process(
            target=_worker,
            args=(
                self.in_queue, 
                self.out_queue, 
                self.state, 
                self.observer_cls, 
                self.observer_args
            ),
        )
        self.worker.start()

    def _wait_worker_init(self, timeout=None):
        s = time.time()
        while True:
            is_ready = self.state[SHR_ON]
            
            if is_ready:
                break
            
            if timeout is not None and (time.time() - s > timeout):
                raise TimeoutError()
            
    def send(self, fun_name, *args, **kwargs):
        payload = cloudpickle.dumps((fun_name, args, kwargs))
        self.in_queue.put(payload)
        
    def barrier(self):
        self.send("barrier")
        _ = self.wait_output()
        return
    
    def wait(self, timeout=None):
        s = time.time()
        while self.state[SHR_ON]:
            if self.in_queue.empty():
                break
            
            if timeout is not None and (time.time() - s > timeout):
                raise TimeoutError()
            
    def wait_output(self, timeout=None):
        s = time.time()
        while self.state[SHR_ON]:
            if timeout is not None and (time.time() - s > timeout):
                raise TimeoutError()
            
            try:
                return self.out_queue.get_nowait()
            except Empty:
                continue

    def __exit__(self, *args):
        self.wait()
        self.state[SHR_ON] = 0
        self.worker.join()
        return self.mm.__exit__(*args)


class _FakeGiven:
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        return
    
    def __call__(self, *args: Any, **kwds: Any) -> Any:
        return self

class _Wrapped(SyncOverseer):
    def __init__(self, instruments, logfile=None):
        super().__init__(instruments, logfile)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        return

    def produce(self, values):
        giver().produce(values)
        
    def giver_call(self, *args, **values):
        giver()(*args, **values)

class AsyncGiver(Giver):
    def __init__(self, remote_worker, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.remote_worker = remote_worker
        
    def produce(self, values):
        self.remote_worker.send("produce", values)
        
    def __call__(self, *args, **values):
        self.remote_worker.send("giver_call", *args, **values)

class AsyncOverseer(SyncOverseer):
    def require(self, *instruments):
        self.remote.send("required", *instruments)
        self.remote.barrier()
        
    def advance_observers(self, phase):
        self.remote.send("advance_observers", phase)
        self.remote.barrier()
        
    def _add_prepare_observer(self):
        self.remote.send("_add_prepare_observer")
        self.remote.barrier()
        
    def produce(self, values):
        self.remote.send("produce", values)
        
    def give(self, **data):
        self.remote.send("give", **data)
        
    def _step(self, entry):
        raise NotImplementedError()
        
    def __init__(self, instruments, logfile=None):
        self.remote = ProcWorker(
            _Wrapped,
            ([],),
            20
        ).__enter__()
        
        self._logger = False
        self.given = _FakeGiven()
        
        import giving.api
        from contextvars import ContextVar
        from types import SimpleNamespace
        
        giver = AsyncGiver(self.remote)
        
        giving.api._global_given.set(SimpleNamespace(
            context=ContextVar("context", default=()),
            give=giver,
            given=self.given
        ))
        
        # init
        super().__init__(instruments, logfile)
    
    def log(self, *args):
        print("LOG", args)
        
    def _finish(self):
        super()._finish()
        self.remote.__exit__(None, None, None)

# class Overseer:
#     "init"
#     "parse_args"
#     "load_script"
#     "run_script"
#     "finalize"
    
#     def __init__(self, instruments, logfile=None):
#         self.remote = ProcWorker(
#             RemoteOverseer,
#             (instruments,),
#             20
#         )
        
#     def __call__(self, *args, **kwargs):
#         """Execute the program through the overseer."""
#         try:
#             self._prepare()     # <= this setup given to process the events
#             self._run(*args, **kwargs)
#         except StopProgram as stp:
#             self._on_stop(*stp.args)
#         except BaseException as e:
#             self._on_error(e)
#             raise
#         finally:
#             self._finish()
            
#     def _prepare(self):
#         pass
    
#     def _run(self, *args, **kwargs):
#         # ([
#         #     '--config', '/Tmp/slurm.4290130.0/base/extra/torchvision/voirconf-resnet152_2.D0-b62509f6697d4afee1157e26947abfa9.json', 
#         #     '/home/mila/d/delaunap/milabench/benchmarks/torchvision/main.py', 
#         #     '--precision', 'tf32-fp16', '--lr', '0.01', '--no-stdout', '--epochs', '12', '--model', 'resnet152', '--batch-size', '64'
#         # ],) 
#         # {}
#         pass
    
#     def _on_stop(self, *args):
#         pass
    
#     def _on_error(self, e):
#         self.log({
#             "$event": "error",
#             "$data": {
#                 "type": type(e).__name__, 
#                 "message": str(e),
#             },
#         })
    
#     def _finish(self):
#         pass
    
#     def log(self, *args):
#         pass

#     @contextmanager
#     def run_phase(self, phase: Phase):
#         self.log({"$event": "phase", "$data": {"name": phase.name}})
#         result = exception = None

#         def _set_value(value):
#             nonlocal result
#             result = value

#         try:
#             yield _set_value
#         except BaseException as exc:
#             exception = exc

#         phase.status = "running"
#         phase.value = result
#         phase.exception = exception
        
#         try:
#             # Phase finished
#             self.remote.send(phase)
#             self.remote.barrier()
#             phase.status = "done"
#         except OverseerAbort as exc:
#             raise exc.args[0]
#         else:
#             if exception:
#                 raise exception