import json
import os
import shutil
import subprocess
import sys

from ..tools import instrument_definition


def _get_info(requires, command, parse_function):
    if not shutil.which(requires):
        return None
    proc_results = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        return parse_function(json.loads(proc_results.stdout))
    except json.JSONDecodeError:
        print(f"There was a problem with {requires}:")
        print("=" * 80)
        print(proc_results.stderr, file=sys.stderr)
        print("=" * 80)
        return None


def get_cuda_info():
    return _get_info("nvidia-smi", "nvidia-smi -x -q | xml2json", parse_cuda)


def get_rocm_info():
    return _get_info("rocm-smi", "rocm-smi -a --showmeminfo vram --json", parse_rocm)


def parse_cuda(info):
    def parse_num(n):
        n, units = n.split(" ")
        if units == "MiB":
            return int(n)
        elif units == "C" or units == "W":
            return float(n)
        elif units == "%":
            return float(n) / 100
        else:
            raise ValueError(n)

    def parse_gpu(gpu, gid):
        mem = gpu["fb_memory_usage"]
        used = parse_num(mem["used"])
        total = parse_num(mem["total"])
        return {
            "device": gid,
            "product": gpu["product_name"],
            "memory": {
                "used": used,
                "total": total,
            },
            "utilization": {
                "compute": parse_num(gpu["utilization"]["gpu_util"]),
                "memory": used / total,
            },
            "temperature": parse_num(gpu["temperature"]["gpu_temp"]),
            "power": parse_num(gpu["power_readings"]["power_draw"]),
            "selection_variable": "CUDA_VISIBLE_DEVICES",
        }

    data = info["nvidia_smi_log"]
    gpus = data["gpu"]
    if not isinstance(gpus, list):
        gpus = [gpus]

    return {i: parse_gpu(g, str(i)) for i, g in enumerate(gpus)}


def parse_rocm(info):
    def parse_gpu(gpu, gid):
        used = int(gpu["VRAM Total Used Memory (B)"])
        total = int(gpu["VRAM Total Memory (B)"])
        return {
            "device": gid,
            "product": "ROCm Device",
            "memory": {
                "used": used // (1024**2),
                "total": total // (1024**2),
            },
            "utilization": {
                "compute": float(gpu["GPU use (%)"]) / 100,
                "memory": used / total,
            },
            "temperature": float(gpu["Temperature (Sensor edge) (C)"]),
            "power": float(gpu["Average Graphics Package Power (W)"]),
            "selection_variable": "ROCR_VISIBLE_DEVICES",
        }

    results = {}
    for k, v in info.items():
        x, y, cnum = k.partition("card")
        if x != "" or y != "card":
            continue
        results[cnum] = parse_gpu(v, cnum)

    return results


def get_gpu_info(arch=None):
    if arch is None:
        cuda = get_cuda_info()
        rocm = get_rocm_info()
        if cuda and rocm:
            raise Exception(
                "Milabench found both CUDA and ROCM-compatible GPUs and does not"
                " know which kind to use. Please set $MILABENCH_GPU_ARCH to 'cuda',"
                " 'rocm' or 'cpu'."
            )
        elif cuda:
            arch = "cuda"
            return cuda
        elif rocm:
            arch = "rocm"
            return rocm
        else:
            arch = "cpu"
            return {}

    if arch == "cuda":
        results = get_cuda_info()
    elif arch == "rocm":
        results = get_rocm_info()
    elif arch == "cpu":
        results = {}
    else:
        raise ValueError(
            "Could not infer the gpu architecture because both cuda "
            "and rocm-compatible gpus were found. Please specify "
            "arch in ('cuda', 'rocm', 'cpu')"
        )

    results["arch"] = arch
    return results


@instrument_definition
def gpu_monitor(ov, poll_interval=10):
    yield ov.phases.load_script

    visible = os.environ.get("CUDA_VISIBLE_DEVICES", None) or os.environ.get(
        "ROCR_VISIBLE_DEVICES", None
    )
    if visible:
        ours = visible.split(",")
    else:
        ours = [str(x) for x in range(100)]

    def monitor(_):
        data = {
            gpu["device"]: {
                "memory": [gpu["memory"]["used"], gpu["memory"]["total"]],
                "load": gpu["utilization"]["compute"],
                "temperature": gpu["temperature"],
            }
            for gpu in get_gpu_info().values()
            if gpu["device"] in ours
        }
        ov.give(task="main", gpudata=data)

    ov.given.throttle(poll_interval) >> monitor

    try:
        yield ov.phases.run_script
    finally:
        monitor(None)
