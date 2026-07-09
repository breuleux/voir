import json
from pathlib import Path

import pytest

from voir.instruments.gpu import tt as tt_backend
from voir.instruments.gpu.common import NotAvailable


SYSFS_ENTRY = {
    "device_id": 0,
    "board_info": {"board_type": "n300", "bus_id": "0000:31:00.0"},
    "telemetry": {
        "power": 22.0,
        "asic_temperature": 34.0,
        "current": 24.0,
        "voltage": 0.92,
        "aiclk": 1000.0,
    },
    "limits": {},
}

GPU_DEVICE = {
    "board_info": SYSFS_ENTRY["board_info"],
    "telemetry": {
        "power": 22.0,
        "asic_temperature": 34.0,
        "current": 24.0,
        "voltage": 0.92,
        "aiclk": 1000.0,
    },
    "limits": {},
    "_device_id": 0,
    "_source": "sysfs",
}


@pytest.fixture
def mock_sysfs(monkeypatch):
    monkeypatch.setattr(tt_backend, "discover_sysfs_devices", lambda: [SYSFS_ENTRY])


def test_discover_sysfs_devices_live():
    if not Path("/sys/class/tenstorrent").is_dir():
        pytest.skip("Tenstorrent sysfs not available")

    devices = tt_backend.discover_sysfs_devices()
    assert devices
    dev0 = devices[0]
    assert dev0["board_info"]["board_type"]
    assert dev0["telemetry"]["power"] >= 0
    assert dev0["telemetry"]["asic_temperature"] >= 0


def test_fetch_devices_from_sysfs(mock_sysfs):
    devices = tt_backend.fetch_devices()
    assert devices[0]["_source"] == "sysfs"
    assert devices[0]["telemetry"]["power"] == 22.0


def test_make_gpu_info(mock_sysfs):
    smi = tt_backend.DeviceSMI()
    info = smi.get_gpus_info()
    assert info[0]["source"] == "sysfs"
    assert info[0]["power"] == 22.0
    assert info[0]["temperature"] == 34.0
    assert info[0]["utilization"]["compute"] == pytest.approx(22.0 / 85.0)
    assert info[0]["memory"]["total"] == 12 * 1024
    assert info[0]["memory"]["used"] == -1


def test_make_gpu_info_respects_selection():
    infos = tt_backend.make_gpu_infos([GPU_DEVICE], ["0"])
    assert list(infos) == [0]

    infos = tt_backend.make_gpu_infos([GPU_DEVICE], ["1"])
    assert infos == {}


def test_board_gddr_mib():
    assert tt_backend.board_gddr_mib("n300 L") == 12 * 1024
    assert tt_backend.board_gddr_mib("n150d") == 12 * 1024
    assert tt_backend.board_gddr_mib("unknown") == -1


def test_report_dram_usage():
    tt_backend.clear_dram_usage()
    tt_backend.report_dram_usage(0, used_mib=4096, total_mib=12288)
    infos = tt_backend.make_gpu_infos([GPU_DEVICE], ["0"])
    assert infos[0]["memory"]["used"] == 4096
    assert infos[0]["memory"]["total"] == 12288
    assert infos[0]["utilization"]["memory"] == pytest.approx(4096 / 12288)
    tt_backend.clear_dram_usage()


def test_extract_snapshot_json_with_prefix():
    snapshot = {
        "host_info": {"Driver": "TT-KMD 2.8.0"},
        "host_sw_vers": {"tt_smi": "5.3.1"},
        "device_info": [],
    }
    stdout = "Gathering Information...\n" + json.dumps(snapshot)
    data = tt_backend._extract_snapshot_json(stdout)
    assert data["host_sw_vers"]["tt_smi"] == "5.3.1"


def test_fetch_snapshot_missing_binary(monkeypatch):
    monkeypatch.delenv("TT_SMI_PATH", raising=False)
    monkeypatch.setattr(tt_backend.shutil, "which", lambda _: None)
    assert tt_backend.fetch_snapshot() is None


def test_system_info_merges_sysfs_and_tt_smi(mock_sysfs, monkeypatch):
    monkeypatch.setattr(
        tt_backend,
        "fetch_snapshot",
        lambda: {
            "host_info": {"Driver": "TT-KMD 2.8.0"},
            "host_sw_vers": {"tt_smi": "5.3.1", "tt_umd": "0.9.5", "pyluwen": "0.8.5"},
        },
    )
    monkeypatch.setattr(tt_backend, "_sysfs_driver_version", lambda: "2.8.0")

    info = tt_backend.DeviceSMI().system_info()
    assert info["SOURCE"] == "sysfs"
    assert info["DRIVER"] == "TT-KMD 2.8.0"
    assert info["TT_SMI"] == "5.3.1"
    assert info["TT_UMD"] == "0.9.5"
    assert info["PYLUWEN"] == "0.8.5"


def test_system_info_sysfs_only_when_tt_smi_missing(mock_sysfs, monkeypatch):
    monkeypatch.setattr(tt_backend, "fetch_snapshot", lambda: None)
    monkeypatch.setattr(tt_backend, "_sysfs_driver_version", lambda: "2.8.0")

    info = tt_backend.DeviceSMI().system_info()
    assert info["DRIVER"] == "2.8.0"
    assert "TT_SMI" not in info


def test_device_smi_no_devices(monkeypatch):
    monkeypatch.setattr(tt_backend, "discover_sysfs_devices", lambda: [])
    with pytest.raises(NotAvailable, match="No Tenstorrent devices"):
        tt_backend.DeviceSMI()
