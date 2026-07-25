import datetime
import json
import os

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

QUERY = """
    SELECT timestamp, id, reading
    FROM all_readings
    WHERE model = %s
      AND timestamp >= now() - (%s * interval '1 hour')
    ORDER BY timestamp ASC
"""

SERIES_COLORS = ["#2a78d6", "#eb6834"]  # categorical slots 1 (blue) / 2 (orange)


def c_to_f(celsius):
    return celsius * 9 / 5 + 32


def fetch_readings():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(QUERY, (MODEL, LOOKBACK_HOURS))
            return cursor.fetchall()


def parse_rows(rows):
    # device id -> probe name -> (list of timestamps, list of fahrenheit temps)
    series = {}
    for timestamp, device_id, reading in rows:
        try:
            payload = json.loads(reading)
        except json.JSONDecodeError:
            continue

        for probe_key, probe_label in (
            ("temperature_1_C", "Probe 1"),
            ("temperature_2_C", "Probe 2"),
        ):
            if probe_key not in payload:
                continue
            device_series = series.setdefault(device_id, {})
            times, temps = device_series.setdefault(probe_label, ([], []))
            times.append(timestamp)
            temps.append(c_to_f(payload[probe_key]))

    return series


def plot_series(series):
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    multiple_devices = len(series) > 1
    for device_id, probes in series.items():
        for probe_index, (probe_label, (times, temps)) in enumerate(probes.items()):
            color = SERIES_COLORS[probe_index % len(SERIES_COLORS)]
            label = f"{probe_label} (id {device_id})" if multiple_devices else probe_label
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
    ax.tick_params(colors="#898781")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()

    ax.grid(True, color="#e1e0d9", linewidth=0.8)
    for spine_name, spine in ax.spines.items():
        if spine_name in ("top", "right"):
            spine.set_visible(False)
        else:
            spine.set_color("#c3c2b7")

    ax.legend(frameon=False, labelcolor="#52514e")
    fig.tight_layout()
    return fig


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


if __name__ == "__main__":
    main()
