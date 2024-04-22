import os

from .common import NotAvailable


IMPORT_ERROR = None
try:
    # python -m pip install --index-url https://pypi.anaconda.org/intel/simple dpctl
    import dpctl
except ImportError as err:
    IMPORT_ERROR = err


def fix_num(n):
    if n == "N/A":
        n = None
    return n


def parse_gpu(gpu, gid):
    # device.vendor          => 'Intel(R) Corporation'
    # device.name            => 'Intel(R) Data Center GPU Max 1550'
    # device.local_mem_size  => 32768               (in bytes) 'Intel(R) Xeon(R) Platinum 8468V' 
    #                        => 131072              (in bytes) 'Intel(R) Data Center GPU Max 1550'
    # device.max_mem_alloc_size => 1082076110848    (in bytes)
    #                           =>   65267564544    (in bytes) 'Intel(R) Data Center GPU Max 1550'
    # device.get_filter_string() => 'opencl:cpu:0'      'Intel(R) Xeon(R) Platinum 8468V' 
    # device.get_filter_string() => 'opencl:gpu:0'      'Intel(R) Data Center GPU Max 1550'
    #
    # >>> dpctl.get_devices()[1].print_device_info()
    #     Name            Intel(R) Data Center GPU Max 1550
    #     Driver version  23.30.26918.50
    #     Vendor          Intel(R) Corporation
    #     Filter string   opencl:gpu:0

    return {
        "device": gpu.get_filter_string(),
        "product": gpu.name,
        "memory": {
            "used": 0,
            "total": gpu.max_mem_alloc_size,
        },
        "utilization": {
            "compute": 1,
            "memory": 0,
        },
        "temperature": 1,
        "power": 1,
        #
        # ONEAPI_DEVICE_SELECTOR='opencl:0,1,2,3'
        #
        "selection_variable": "ONEAPI_DEVICE_SELECTOR",
    }


def get_devices():
    return dpctl.get_devices()


def get_gpus():
    gpus = []
    cpus = []

    for device in get_devices():
        # GPUs are shown as level_zero AND openCL
        if device.is_gpu and 'level_zero' not in device.get_filter_string():
            gpus.append(device)

        if device.is_cpu:
            cpus.append(device)

    return gpus



def is_installed():
    return IMPORT_ERROR is None


class DeviceSMI:
    def __init__(self) -> None:
        if IMPORT_ERROR is not None:
            raise IMPORT_ERROR
        
        self.gpus = get_gpus()

    @property
    def arch(self):
        return "xpu"

    @property
    def visible_devices(self):
        return os.environ.get("SYCL_DEVICE_FILTER", None)

    def get_gpus_info(self, selection=None):

        return {i: parse_gpu(g, i) for i, g in enumerate(self.gpus)}

    def close(self):
        pass
