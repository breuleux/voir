import glob
import os
import time
import traceback
from threading import Thread

from ...errors import NotAvailable
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
DEVICESMI = None
ARCH = None


def get_backends():
    global BACKENDS
    return BACKENDS.keys()


def _is_backend_available(backend):
    try:
        smi = backend.DeviceSMI()

        if len(smi.get_gpus_info()) > 0:
            return True

    except NotAvailable:
        return False


def deduce_backend():
    suitable = []
    for k, backend in BACKENDS.items():
        if backend.is_installed() and _is_backend_available(backend):
            suitable.append(k)

    if len(suitable) > 1:
        options = ", ".join(get_backends())
        raise Exception(
            f"Milabench found multiple vendors ({suitable}) and does not "
            f"know which kind to use. Please set $MILABENCH_GPU_ARCH to one of {options}."
        )

    elif len(suitable) == 0:
        return "cpu"

    return suitable[0]


def select_backend(arch=None):
    global BACKEND, DEVICESMI, ARCH

    if ARCH is not None and ARCH == arch:
        return DEVICESMI, ARCH
    else:
        _reset()

    if arch is None:
        arch = deduce_backend()

    ARCH = arch
    BACKEND = BACKENDS.get(arch)

    if BACKEND is not None:
        if BACKEND.is_installed():
            DEVICESMI = BACKEND.DeviceSMI()
        else:
            raise NotAvailable(f"{arch} is not installed")

    return DEVICESMI, ARCH


def _reset():
    global BACKEND, DEVICESMI, ARCH
    BACKEND = None
    DEVICESMI = None
    ARCH = None


def get_visible_devices():
    global BACKEND
    return BACKEND.get_visible_devices()


def get_gpu_info(arch=None):
    monitor, arch = select_backend(arch)

    result = {}
    if monitor is not None:
        result = monitor.get_gpus_info()

    return {"arch": arch, "gpus": result}


@instrument_definition
def gpu_monitor(ov, poll_interval=10, arch=None):
    yield ov.phases.load_script

    visible = get_visible_devices()

    if visible:
        ours = visible.split(",")
    else:
        ours = [str(x) for x in range(100)]

    def monitor():
        data = {
            gpu["device"]: {
                "memory": [
                    gpu["memory"]["used"],
                    gpu["memory"]["total"],
                ],
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
