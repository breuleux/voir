import os
import time
import glob
import traceback
from threading import Thread

from ...tools import instrument_definition
from ..utils import Monitor as Monitor2


def find_monitors():
    """Look for device monitor implementation (AMD or ROCm)"""
    backends = {}
    base = __file__
    base_module = "voir.instruments.gpu"
    module_path = os.path.dirname(os.path.abspath(base))
    pattern = os.path.join(module_path, "[A-Za-z]*")

    for module_path in glob.glob(pattern, recursive=False):
        module_file = module_path.split(os.sep)[-1]

        if module_file == "__init__.py":
            continue

        module_name = module_file.split(".py")[0]

        try:
            module = __import__(".".join([base_module, module_name]), fromlist=[""])
        except ImportError:
            print(traceback.format_exc())
            continue

        backends[module_name] = module

    return backends


BACKENDS = find_monitors()
BACKEND = None
MONITOR = None
ARCH = None


def get_backends():
    global BACKENDS
    return BACKENDS.keys()


def select_backend(arch=None):
    global BACKEND, MONITOR, ARCH

    if ARCH is not None:
        return MONITOR, ARCH

    if arch is None:
        suitable = []

        for k, backend in BACKENDS.items():
            if backend.is_available():
                try:
                    m = backend.Monitor()
                    suitable.append(k)
                except Exception:
                    pass

        if len(suitable) > 1:
            raise Exception(
                f"Milabench found multiple vendors ({suitable}) and does not"
                " know which kind to use. Please set $MILABENCH_GPU_ARCH to 'cuda',"
                " 'rocm' or 'cpu'."
            )
        elif len(suitable) == 0:
            arch = "cpu"
        else:
            arch = suitable[0]

    ARCH = arch
    BACKEND = BACKENDS.get(arch)

    if BACKEND is not None and BACKEND.is_available():
        MONITOR = BACKEND.Monitor()

    return MONITOR, ARCH


def _reset():
    global BACKEND, MONITOR, ARCH
    BACKEND = None
    MONITOR = None
    ARCH = None


def get_gpu_info(arch=None):
    monitor, arch = select_backend(arch)

    result = {}
    if monitor is not None:
        result = monitor.get_gpus_info()

    return {"arch": arch, "gpus": result}


class Monitor(Thread):
    # Keeping this class temporarily to avoid a breakage in milabench

    def __init__(self, ov, delay, func):
        super().__init__(daemon=True)
        self.ov = ov
        self.stopped = False
        self.delay = delay
        self.func = func

    def run(self):
        while not self.stopped:
            time.sleep(self.delay)
            self.func()

    def stop(self):
        self.stopped = True


@instrument_definition
def gpu_monitor(ov, poll_interval=10, arch=None):
    yield ov.phases.load_script

    visible = os.environ.get("CUDA_VISIBLE_DEVICES", None) or os.environ.get(
        "ROCR_VISIBLE_DEVICES", None
    )
    if visible:
        ours = visible.split(",")
    else:
        ours = [str(x) for x in range(100)]

    def monitor():
        data = {
            gpu["device"]: {
                "memory": [gpu["memory"]["used"], gpu["memory"]["total"]],
                "load": gpu["utilization"]["compute"],
                "temperature": gpu["temperature"],
            }
            for gpu in get_gpu_info(arch)["gpus"].values()
            if str(gpu["device"]) in ours
        }
        ov.give(task="main", gpudata=data)

    monitor_thread = Monitor2(poll_interval, monitor)
    monitor_thread.start()
    try:
        yield ov.phases.run_script
    finally:
        monitor_thread.stop()
        monitor()
