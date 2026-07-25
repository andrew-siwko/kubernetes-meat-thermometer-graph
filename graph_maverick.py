import datetime
import json
import os
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from psycopg import connect

# Connection info (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD) comes from the
# environment - psycopg.connect() with no arguments reads the standard libpq
# env vars automatically.

MODEL = os.environ.get("MAVERICK_MODEL", "Maverick-ET73")
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", 8))
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "/output/maverick-temperature.png")
GRAPH_MIN_F = float(os.environ.get("GRAPH_MIN_F", 0))
GRAPH_MAX_F = float(os.environ.get("GRAPH_MAX_F", 250))

SCP_HOST = os.environ.get("SCP_HOST", "lts.siwko.org")
SCP_PORT = os.environ.get("SCP_PORT", "8022")
SCP_USER = os.environ.get("SCP_USER", "root")
SCP_PATH = os.environ.get("SCP_PATH", "/var/www/html/maverick-temperature.png")
SCP_KEY_PATH = os.environ.get("SCP_KEY_PATH", "/secrets/ssh/id_ed25519")
SCP_KNOWN_HOSTS_PATH = os.environ.get("SCP_KNOWN_HOSTS_PATH", "/secrets/ssh/known_hosts")

QUERY = """
    SELECT timestamp, id, reading
    FROM all_readings
    WHERE model = %s
      AND timestamp >= now() - (%s * interval '1 hour')
    ORDER BY timestamp ASC
"""

SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # categorical slots 1-4


def c_to_f(celsius):
    return celsius * 9 / 5 + 32


def fetch_readings():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(QUERY, (MODEL, LOOKBACK_HOURS))
            return cursor.fetchall()


def parse_rows(rows):
    # device id -> (list of timestamps, list of fahrenheit temps)
    series = {}
    for timestamp, device_id, reading in rows:
        try:
            payload = json.loads(reading)
        except json.JSONDecodeError:
            continue

        if "temperature_1_C" not in payload:
            continue
        times, temps = series.setdefault(device_id, ([], []))
        times.append(timestamp)
        temps.append(c_to_f(payload["temperature_1_C"]))

    return series


def plot_series(series):
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    multiple_devices = len(series) > 1
    for device_index, (device_id, (times, temps)) in enumerate(series.items()):
        color = SERIES_COLORS[device_index % len(SERIES_COLORS)]
        label = f"id {device_id}" if multiple_devices else None
        ax.plot(
            times,
            temps,
            color=color,
            linewidth=2,
            solid_capstyle="round",
            label=label,
        )

    ax.set_title(
        f"{MODEL} temperature — last {LOOKBACK_HOURS}h",
        color="#0b0b0b",
        fontsize=14,
        loc="left",
    )
    ax.set_ylabel("Temperature (°F)", color="#52514e")
    ax.set_ylim(GRAPH_MIN_F, GRAPH_MAX_F)
    ax.tick_params(colors="#898781")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    ax.grid(True, color="#e1e0d9", linewidth=0.8)
    for spine_name, spine in ax.spines.items():
        if spine_name in ("top", "right"):
            spine.set_visible(False)
        else:
            spine.set_color("#c3c2b7")

    if multiple_devices:
        ax.legend(frameon=False, labelcolor="#52514e")
    fig.tight_layout()
    return fig


def scp_graph():
    destination = f"{SCP_USER}@{SCP_HOST}:{SCP_PATH}"
    subprocess.run(
        [
            "scp",
            "-P", SCP_PORT,
            "-i", SCP_KEY_PATH,
            "-o", f"UserKnownHostsFile={SCP_KNOWN_HOSTS_PATH}",
            "-o", "StrictHostKeyChecking=yes",
            OUTPUT_PATH,
            destination,
        ],
        check=True,
    )
    print(f"copied {OUTPUT_PATH} to {destination}", flush=True)


def main():
    rows = fetch_readings()
    if not rows:
        print(
            f"no {MODEL} readings in the last {LOOKBACK_HOURS}h, "
            f"leaving previous graph at {OUTPUT_PATH} in place",
            flush=True,
        )
        return

    series = parse_rows(rows)
    fig = plot_series(series)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())
    print(f"wrote {OUTPUT_PATH} from {len(rows)} readings", flush=True)

    scp_graph()


if __name__ == "__main__":
    main()
