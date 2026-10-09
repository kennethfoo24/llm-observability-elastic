"""NVIDIA GPU monitoring: the `nvidia_gpu` integration (DCGM exporter scraped by the prometheus module, stream `stats`)
and the `nvidia_gpu_otel` content package (DCGM metrics through the OpenTelemetry prometheus receiver, written to
metrics-nvidia_gpu.otel-default because its dashboard queries exactly that index).

Estate: two fictional GPU servers with four NVIDIA A100 80GB each. gpu-node-a runs a long training job (high utilisation,
big framebuffer, hot), gpu-node-b serves inference (utilisation follows the working day). A rare XID error shows up on a
GPU: that sample is the XID error series (the `err_code` / `err_msg` dimension the dashboards group by) instead of the normal one.
"""
from __future__ import annotations

import math
from .. import engine, profile, registry
from ..registry import Ctx, Generator
from . import devtools, infra
from .devtools import S
from .infra_otel import host_res, metric_doc, scope, stream

NODES = [("gpu-node-a", "training"), ("gpu-node-b", "inference")]
GPUS_PER_NODE = 4
MODEL = "NVIDIA A100-SXM4-80GB"
DRIVER = "550.90.07"
FB_TOTAL = 81920  # MiB
N_GPU = len(NODES) * GPUS_PER_NODE
XID = [(31, "GPU memory page fault", 0.4), (43, "GPU stopped processing", 0.3), (13, "Graphics Engine Exception", 0.15),
       (79, "GPU has fallen off the bus", 0.05), (63, "ECC page retirement or row remapping event", 0.1)]
ERROR_P = 0.002  # per sample (one per GPU every 3 minutes): about one XID per GPU every two days; that sample carries the error series

STATS = S["nvidia_gpu/stats"]
engine.NO_ID_PREFIXES.append("metrics-nvidia_gpu.stats-")
OTEL = stream("nvidia_gpu_otel", "0.3.0", "nvidia_gpu.otel", "metrics", namespace="default")


def gpu_of(i: int) -> tuple[str, str, int, str]:
    """(node, role, gpu index, uuid) of one of the eight GPUs."""
    node, role = NODES[(i % N_GPU) // GPUS_PER_NODE]
    g = i % GPUS_PER_NODE
    h = f"{infra.stable('gpu-uuid', node, g):08x}{infra.stable('gpu-uuid2', node, g):08x}"
    return node, role, g, f"GPU-{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32].ljust(12, '0')}"


def levels(c: Ctx, node: str, role: str, g: int) -> dict:
    """The instantaneous state of one GPU: utilisation fractions, memory, temperature, power, clocks."""
    r = c.rng
    minute = c.ts.hour * 60 + c.ts.minute
    if role == "training":
        util = 0.9 + 0.06 * math.sin(minute / 7.0 + g) + r.uniform(-0.03, 0.03)
        if (minute + 5 * g) % 37 == 0:  # checkpoint: the GPU idles for a minute
            util *= 0.25
        mem_used = 64000 + 1800 * g + 1500 * math.sin(minute / 90.0) + r.uniform(-300, 300)
        mem_util = util * 0.62
    else:
        util = 0.06 + 0.78 * min(c.load, 1.5) / 1.5 * (0.85 + 0.15 * math.sin(minute / 11.0 + g * 2)) + r.uniform(-0.04, 0.04)
        mem_used = 17500 + 21000 * min(c.load, 1.5) / 1.5 + 900 * g + r.uniform(-400, 400)
        mem_util = util * 0.45
    util = min(max(util, 0.01), 0.99)
    mem_used = min(max(mem_used, 1200), FB_TOTAL - 800)
    temp = 36 + 44 * util ** 1.3 + (3 if g % 2 else 0) + r.uniform(-1.2, 1.2)
    power = 62 + 330 * util + r.uniform(-8, 8)
    thermal = temp > 79
    sm_clock = 1410 - (160 if thermal else 0) - (240 if util < 0.15 else 0) + r.choice([0, 0, 15, -15])
    return {"util": util, "mem_used": mem_used, "mem_util": min(mem_util, 0.95), "temp": temp, "power": power, "sm_clock": sm_clock,
            "mem_clock": 1593 if util > 0.1 else 1215, "enc": 3.0 * r.random() if role == "inference" else 0.0,
            "dec": 6.0 * r.random() * util if role == "inference" else 0.0}


def rate(role: str, c: Ctx, k: float):
    """Per second rate of a counter that follows the node's role: constant on the training node, the working day profile on the inference node
    (a LoadRate integrates to a monotonic counter; a rate computed from the instantaneous, noisy utilisation would not)."""
    return 0.9 * k if role == "training" else infra.LoadRate(0.08 * k, 0.78 * k, c.load)


def _error(c: Ctx) -> tuple[int, str] | None:
    if c.rng.random() >= ERROR_P:
        return None
    pick = c.rng.choices(XID, weights=[w for _, _, w in XID])[0]
    return pick[0], pick[1]


# ----------------------------------------------------- nvidia_gpu.stats (final shaped metrics document) -------------------------------
def _stats(c: Ctx) -> dict:
    node, role, g, uuid = gpu_of(c.i)
    ts = c.ts
    lv = levels(c, node, role, g)
    err = _error(c)
    d = devtools.metric_base("nvidia_gpu/stats", node)
    key = f"{node}{g}"
    labels = {"device": f"nvidia{g}", "driver_version": DRIVER, "gpu": str(g), "hostname": node, "job": "dcgm-exporter", "model_name": MODEL,
              "pci_bus_id": f"00000000:{0x17 + g * 0x20:02X}:00.0", "uuid": uuid}
    gpu = {"clock": {"mem_frequency": lv["mem_clock"], "streaming_multiprocessor_frequency": lv["sm_clock"]},
           "device": {"brand": "NVIDIA A100", "ecc_info_rom_version": "6.16", "power_info_rom_version": "2.1", "serial_number": f"1650{stable_n(key)}",
                      "vbios_version": "92.00.36.00.02"},
           "labels": labels,
           "memory": {"framebuffer": {"free_size": round(FB_TOTAL - lv["mem_used"], 1), "used_size": round(lv["mem_used"], 1)}},
           "power": {"usage": round(lv["power"], 3), "energy_consumption_total": infra.counter(ts, rate(role, c, 390000.0), "nv-energy" + key, False)},
           "temperature": {"gpu": round(lv["temp"]), "memory": round(lv["temp"] + 6 + c.rng.random() * 3)},
           "utilization": {"gpu": {"pct": round(lv["util"] * 100, 1)}, "memory_copy": {"pct": round(lv["mem_util"] * 100, 1)},
                           "encoder": {"pct": round(lv["enc"], 1)}, "decoder": {"pct": round(lv["dec"], 1)}},
           "pcie": {"rx_bytes": infra.counter(ts, rate(role, c, 1.3e9), "nv-rx" + key, False), "tx_bytes": infra.counter(ts, rate(role, c, 1.0e9), "nv-tx" + key, False),
                    "replay": infra.counter(ts, 0.0004, "nv-replay" + key, False)},
           "nvlink": {"bandwidth_total": infra.counter(ts, rate(role, c, 6.5e9), "nv-nvl" + key, False), "bandwidth_l0_total": infra.counter(ts, rate(role, c, 1.6e9), "nv-nvl0" + key, False),
                      "replay_errors": {"count": infra.counter(ts, 0.0002, "nv-nvre" + key, False)},
                      "recovery_errors": {"count": 0}, "data_crc_errors": {"count": infra.counter(ts, 0.0001, "nv-nvcrc" + key, False)},
                      "flowcontrol_crc_errors": {"count": 0}},
           "ecc": {"single_bit_volatile": {"count": infra.counter(ts, 0.00002, "nv-sbv" + key, False)}, "double_bit_volatile": {"count": 0},
                   "single_bit_persistent": {"count": infra.counter(ts, 0.00001, "nv-sbp" + key, False)}, "double_bit_persistent": {"count": 0}},
           "retired": {"pending": {"count": 0}, "single_bit_errors": {"count": 0}, "double_bit_errors": {"count": 0}},
           "remapped": {"correctable_remapped_rows": {"count": 0}, "uncorrectable_remapped_rows": {"count": 0}, "failed_remapped_rows": {"count": 0}},
           "throttling": {"power": {"us": infra.counter(ts, rate(role, c, 13000.0), "nv-thp" + key, False)},
                          "thermal": {"us": infra.counter(ts, 60000.0 if role == "training" else 400.0, "nv-tht" + key, False)},
                          "board_limit": {"us": infra.counter(ts, 800, "nv-thb" + key, False)}, "low_utilization": {"us": infra.counter(ts, 30000.0 if role == "training" else 300000.0, "nv-thl" + key, False)},
                          "reliability": {"us": 0}, "sync_boost": {"us": 0}},
           "dcp": {"sm": {"active": round(lv["util"] * 0.96, 3), "occupancy": round(lv["util"] * 0.55, 3)}, "tensor_pipe": {"active": round(lv["util"] * (0.7 if role == "training" else 0.2), 3)},
                   "fp16_pipe": {"active": round(lv["util"] * 0.45, 3)}, "fp32_pipe": {"active": round(lv["util"] * 0.12, 3)}, "fp64_pipe": {"active": 0.0},
                   "graphics_engine": {"active": round(lv["util"] * 0.97, 3)}, "dram": {"active": round(lv["mem_util"] * 0.8, 3)}},
           "license_vgpu_status": 0, "up": "1"}
    if err:
        gpu["labels"]["err_code"] = str(err[0])
        gpu["labels"]["err_msg"] = err[1]
        gpu["error"] = {"xid": float(err[0])}
    d["gpu"] = gpu
    d["service"] = {"address": f"http://{node}:9400/metrics", "type": "prometheus"}
    d["event"]["dataset"] = "nvidia_gpu.stats"
    d["metricset"] = {"name": "collector", "period": 10000}
    d["@timestamp"] = profile.iso(ts)
    d.pop("server", None)
    return d


def stable_n(key: str) -> str:
    return f"{infra.stable('serial', key) % 10_000_000:07d}"


# ----------------------------------------------------- nvidia_gpu.otel (DCGM metrics through the OTel prometheus receiver) ------------
def _otel(c: Ctx) -> dict:
    node, role, g, uuid = gpu_of(c.i)
    ts = c.ts
    lv = levels(c, node, role, g)
    err = _error(c)
    attrs = {"UUID": uuid, "gpu": str(g), "device": f"nvidia{g}", "modelName": MODEL, "Hostname": node, "pci_bus_id": f"00000000:{0x17 + g * 0x20:02X}:00.0",
             "DCGM_FI_DRIVER_VERSION": DRIVER}
    m = {"DCGM_FI_DEV_GPU_UTIL": round(lv["util"] * 100.0, 1), "DCGM_FI_DEV_MEM_COPY_UTIL": round(lv["mem_util"] * 100.0, 1),
         "DCGM_FI_DEV_ENC_UTIL": round(lv["enc"], 1), "DCGM_FI_DEV_DEC_UTIL": round(lv["dec"], 1), "DCGM_FI_DEV_GPU_TEMP": round(lv["temp"]),
         "DCGM_FI_DEV_POWER_USAGE": round(lv["power"], 2), "DCGM_FI_DEV_FB_USED": round(lv["mem_used"]), "DCGM_FI_DEV_FB_FREE": round(FB_TOTAL - lv["mem_used"]),
         "DCGM_FI_DEV_SM_CLOCK": lv["sm_clock"], "DCGM_FI_DEV_MEM_CLOCK": lv["mem_clock"]}
    kinds = {k: "gd" if isinstance(v, float) else "gl" for k, v in m.items()}
    if err:
        attrs["err_code"] = str(err[0])
        attrs["err_msg"] = err[1]
        m = {"DCGM_FI_DEV_XID_ERRORS": float(err[0])}
        kinds = {"DCGM_FI_DEV_XID_ERRORS": "gd"}
    doc = metric_doc(OTEL, ts, host_res(node, "dcgm-exporter", {"service.version": "3.3.6", "k8s.node.name": node}), scope("prometheusreceiver"), attrs, m, kinds)
    return doc


registry.register(
    "devtools",
    Generator(STATS, _stats, mode="entities", entities=N_GPU, every_min=3),
    Generator(OTEL, _otel, mode="entities", entities=N_GPU, every_min=3),
)
