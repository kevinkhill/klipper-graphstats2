import os
import base64
import datetime
import matplotlib
from yattag import Doc, indent
from typing import Tuple, List
from matplotlib.figure import Figure

MAXBANDWIDTH = 25000.0
MAXBUFFER = 2.0
STATS_INTERVAL = 5.0
TASK_MAX = 0.0025

APPLY_PREFIX = [
    "mcu_awake",
    "mcu_task_avg",
    "mcu_task_stddev",
    "bytes_write",
    "bytes_read",
    "bytes_retransmit",
    "freq",
    "adj",
    "target",
    "temp",
    "pwm",
]


def parse_log(logname, mcu=None):
    if mcu is None:
        mcu = "mcu"
    mcu_prefix = mcu + ":"
    apply_prefix = {p: 1 for p in APPLY_PREFIX}
    with open(logname, "r") as f:
        out = []
        for line in f:
            parts = line.split()
            if not parts or parts[0] not in ("Stats", "INFO:root:Stats"):
                # if parts and parts[0] == 'INFO:root:shutdown:':
                #    break
                continue
            prefix = ""
            keyparts = {}
            for p in parts[2:]:
                if "=" not in p:
                    prefix = p
                    if prefix == mcu_prefix:
                        prefix = ""
                    continue
                name, val = p.split("=", 1)
                if name in apply_prefix:
                    name = prefix + name
                keyparts[name] = val
            if "print_time" not in keyparts:
                continue
            keyparts["#sampletime"] = float(parts[1][:-1])
            out.append(keyparts)
        return out


def setup_matplotlib(output_to_file):
    global matplotlib
    if output_to_file:
        matplotlib.use("Agg")
    import matplotlib.pyplot, matplotlib.dates, matplotlib.font_manager
    import matplotlib.ticker


def find_print_restarts(data):
    runoff_samples = {}
    last_runoff_start = last_buffer_time = last_sampletime = 0.0
    last_print_stall = 0
    for d in reversed(data):
        # Check for buffer runoff
        sampletime = d["#sampletime"]
        buffer_time = float(d.get("buffer_time", 0.0))
        if (
            last_runoff_start
            and last_sampletime - sampletime < 5
            and buffer_time > last_buffer_time
        ):
            runoff_samples[last_runoff_start][1].append(sampletime)
        elif buffer_time < 1.0:
            last_runoff_start = sampletime
            runoff_samples[last_runoff_start] = [False, [sampletime]]
        else:
            last_runoff_start = 0.0
        last_buffer_time = buffer_time
        last_sampletime = sampletime
        # Check for print stall
        print_stall = int(d["print_stall"])
        if print_stall < last_print_stall:
            if last_runoff_start:
                runoff_samples[last_runoff_start][0] = True
        last_print_stall = print_stall
    sample_resets = {
        sampletime: 1
        for stall, samples in runoff_samples.values()
        for sampletime in samples
        if not stall
    }
    return sample_resets


def plot_mcu(data, maxbw):
    # Generate data for plot
    basetime = lasttime = data[0]["#sampletime"]
    lastbw = float(data[0]["bytes_write"]) + float(data[0]["bytes_retransmit"])
    sample_resets = find_print_restarts(data)
    times = []
    bwdeltas = []
    loads = []
    awake = []
    hostbuffers = []
    for d in data:
        st = d["#sampletime"]
        timedelta = st - lasttime
        if timedelta <= 0.0:
            continue
        bw = float(d["bytes_write"]) + float(d["bytes_retransmit"])
        if bw < lastbw:
            lastbw = bw
            continue
        load = float(d["mcu_task_avg"]) + 3 * float(d["mcu_task_stddev"])
        if st - basetime < 15.0:
            load = 0.0
        pt = float(d["print_time"])
        hb = float(d["buffer_time"])
        if hb >= MAXBUFFER or st in sample_resets:
            hb = 0.0
        else:
            hb = 100.0 * (MAXBUFFER - hb) / MAXBUFFER
        hostbuffers.append(hb)
        times.append(datetime.datetime.utcfromtimestamp(st))
        bwdeltas.append(100.0 * (bw - lastbw) / (maxbw * timedelta))
        loads.append(100.0 * load / TASK_MAX)
        awake.append(100.0 * float(d.get("mcu_awake", 0.0)) / STATS_INTERVAL)
        lasttime = st
        lastbw = bw

    # Build plot
    fig, ax1 = matplotlib.pyplot.subplots()
    ax1.set_title("MCU bandwidth and load utilization")
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Usage (%)")
    ax1.plot_date(times, bwdeltas, "g", label="Bandwidth", alpha=0.8)
    ax1.plot_date(times, loads, "r", label="MCU load", alpha=0.8)
    ax1.plot_date(times, hostbuffers, "c", label="Host buffer", alpha=0.8)
    ax1.plot_date(times, awake, "y", label="Awake time", alpha=0.6)
    fontP = matplotlib.font_manager.FontProperties()
    fontP.set_size("x-small")
    ax1.legend(loc="best", prop=fontP)
    ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax1.grid(True)
    return fig


def plot_system(data):
    # Generate data for plot
    lasttime = data[0]["#sampletime"]
    lastcputime = float(data[0]["cputime"])
    times = []
    sysloads = []
    cputimes = []
    memavails = []
    for d in data:
        st = d["#sampletime"]
        timedelta = st - lasttime
        if timedelta <= 0.0:
            continue
        lasttime = st
        times.append(datetime.datetime.utcfromtimestamp(st))
        cputime = float(d["cputime"])
        cpudelta = max(0.0, min(1.5, (cputime - lastcputime) / timedelta))
        lastcputime = cputime
        cputimes.append(cpudelta * 100.0)
        sysloads.append(float(d["sysload"]) * 100.0)
        memavails.append(float(d["memavail"]))

    # Build plot
    fig, ax1 = matplotlib.pyplot.subplots()
    ax1.set_title("System load utilization")
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Load (% of a core)")
    ax1.plot_date(times, sysloads, "-", label="system load", color="cyan", alpha=0.8)
    ax1.plot_date(times, cputimes, "-", label="process time", color="red", alpha=0.8)
    ax2 = ax1.twinx()
    ax2.set_ylabel("Available memory (KB)")
    ax2.plot_date(
        times, memavails, "-", label="system memory", color="yellow", alpha=0.3
    )
    fontP = matplotlib.font_manager.FontProperties()
    fontP.set_size("x-small")
    ax1li, ax1la = ax1.get_legend_handles_labels()
    ax2li, ax2la = ax2.get_legend_handles_labels()
    ax1.legend(ax1li + ax2li, ax1la + ax2la, loc="best", prop=fontP)
    ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax1.grid(True)
    return fig


def plot_mcu_frequencies(data):
    all_keys = {}
    for d in data:
        all_keys.update(d)
    graph_keys = {
        key: ([], [])
        for key in all_keys
        if (key in ("freq", "adj") or (key.endswith(":freq") or key.endswith(":adj")))
    }
    for d in data:
        st = datetime.datetime.utcfromtimestamp(d["#sampletime"])
        for key, (times, values) in graph_keys.items():
            val = d.get(key)
            if val not in (None, "0", "1"):
                times.append(st)
                values.append(float(val))
    est_mhz = {
        key: round((sum(values) / len(values)) / 1000000.0)
        for key, (times, values) in graph_keys.items()
    }

    # Build plot
    fig, ax1 = matplotlib.pyplot.subplots()
    ax1.set_title("MCU frequencies")
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Microsecond deviation")
    for key in sorted(graph_keys):
        times, values = graph_keys[key]
        mhz = est_mhz[key]
        label = "%s(%dMhz)" % (key, mhz)
        hz = mhz * 1000000.0
        ax1.plot_date(times, [(v - hz) / mhz for v in values], ".", label=label)
    fontP = matplotlib.font_manager.FontProperties()
    fontP.set_size("x-small")
    ax1.legend(loc="best", prop=fontP)
    ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax1.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%d"))
    ax1.grid(True)
    return fig


def plot_mcu_frequency(data, mcu):
    all_keys = {}
    for d in data:
        all_keys.update(d)
    graph_keys = {key: ([], []) for key in all_keys if key in ("freq", "adj")}
    for d in data:
        st = datetime.datetime.utcfromtimestamp(d["#sampletime"])
        for key, (times, values) in graph_keys.items():
            val = d.get(key)
            if val not in (None, "0", "1"):
                times.append(st)
                values.append(float(val))

    # Build plot
    fig, ax1 = matplotlib.pyplot.subplots()
    ax1.set_title("MCU '%s' frequency" % (mcu,))
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Frequency")
    for key in sorted(graph_keys):
        times, values = graph_keys[key]
        ax1.plot_date(times, values, ".", label=key)
    fontP = matplotlib.font_manager.FontProperties()
    fontP.set_size("x-small")
    ax1.legend(loc="best", prop=fontP)
    ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax1.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%d"))
    ax1.grid(True)
    return fig


def plot_temperature(data, heaters):
    fig, ax1 = matplotlib.pyplot.subplots()
    ax2 = ax1.twinx()
    for heater in heaters.split(","):
        heater = heater.strip()
        temp_key = heater + ":" + "temp"
        target_key = heater + ":" + "target"
        pwm_key = heater + ":" + "pwm"
        times = []
        temps = []
        targets = []
        pwm = []
        for d in data:
            temp = d.get(temp_key)
            if temp is None:
                continue
            times.append(datetime.datetime.utcfromtimestamp(d["#sampletime"]))
            temps.append(float(temp))
            pwm.append(float(d.get(pwm_key, 0.0)))
            targets.append(float(d.get(target_key, 0.0)))
        ax1.plot_date(times, temps, "-", label="%s temp" % (heater,), alpha=0.8)
        if any(targets):
            label = "%s target" % (heater,)
            ax1.plot_date(times, targets, "-", label=label, alpha=0.3)
        if any(pwm):
            label = "%s pwm" % (heater,)
            ax2.plot_date(times, pwm, "-", label=label, alpha=0.2)
    # Build plot
    ax1.set_title("Temperature of %s" % (heaters,))
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Temperature")
    ax2.set_ylabel("pwm")
    fontP = matplotlib.font_manager.FontProperties()
    fontP.set_size("x-small")
    ax1li, ax1la = ax1.get_legend_handles_labels()
    ax2li, ax2la = ax2.get_legend_handles_labels()
    ax1.legend(ax1li + ax2li, ax1la + ax2la, loc="best", prop=fontP)
    ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax1.grid(True)
    return fig


def save_figure(fig: Figure, output: str):
    fig.set_size_inches(8, 6)
    fig.savefig(output)


def generate_html(out_dir: str, figures: List[Tuple[str, Figure]]):
    doc, tag, text = Doc().tagtext()

    with tag("html"):
        with tag("head"):
            with tag("title"):
                text("klippy.log helper")
        with tag("body"):
            with tag("div"):
                for name, fig in figures:
                    plot_path = os.path.join(os.getcwd(), out_dir, f"{name}.png")
                    print(f"Opening {plot_path}")
                    with open(plot_path, "rb") as f:
                        src = base64.b64encode(f.read()).decode("utf-8")
                        doc.stag("img", src=f"data:image/png;base64,{src}")
                        pass

    with open("klippy.log.html", "w") as f:
        # print(doc.getvalue())
        html = indent(
            doc.getvalue(), indentation="    ", newline="\r\n", indent_text=True
        )
        f.write(html)


def draw_graphs(
    data,
    out_dir: str = "plots",
    # output=None,
    mcu: str = "mcu",
    heater: str = None,
):
    figures: List[Tuple[str, Figure]] = []

    setup_matplotlib(True)
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)

    figures.append(("mcu", plot_mcu(data, MAXBANDWIDTH)))
    figures.append(("mcu_freq", plot_mcu_frequencies(data)))
    figures.append(("system", plot_system(data)))
    figures.append(("heater", plot_temperature(data, heater)))

    for name, fig in figures:
        print(f"Saving {out_dir}/{name}.png")
        save_figure(fig, os.path.join(out_dir, name))

    generate_html(out_dir, figures)
