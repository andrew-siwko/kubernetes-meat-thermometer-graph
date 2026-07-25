import datetime
import json
import os
import subprocess
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from psycopg import connect

# Connection info (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD) comes from the
# environment - psycopg.connect() with no arguments reads the standard libpq
# env vars automatically.

# all_readings.timestamp is naive but stored as UTC (Postgres server TimeZone
# is Etc/UTC - see kubernetes-mosquito/update_reading_age.py for the same
# assumption on this column).
DISPLAY_TZ = ZoneInfo("America/New_York")

MAVERICK_MODEL = os.environ.get("MAVERICK_MODEL", "Maverick-ET73")
ACURITE_MODEL = os.environ.get("ACURITE_MODEL", "Acurite-5n1")
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", 8))
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "/output/maverick-temperature.png")

GRAPH_MIN_F = float(os.environ.get("GRAPH_MIN_F", 0))
GRAPH_MAX_F = float(os.environ.get("GRAPH_MAX_F", 250))
OUTDOOR_MIN_F = float(os.environ.get("OUTDOOR_MIN_F", -20))
OUTDOOR_MAX_F = float(os.environ.get("OUTDOOR_MAX_F", 120))
WIND_MIN_MPH = float(os.environ.get("WIND_MIN_MPH", 0))
WIND_MAX_MPH = float(os.environ.get("WIND_MAX_MPH", 40))

SCP_HOST = os.environ.get("SCP_HOST", "lts.siwko.org")
SCP_PORT = os.environ.get("SCP_PORT", "8022")
SCP_USER = os.environ.get("SCP_USER", "root")
SCP_PATH = os.environ.get("SCP_PATH", "/var/www/html/maverick-temperature.png")
SCP_KEY_PATH = os.environ.get("SCP_KEY_PATH", "/secrets/ssh/id_ed25519")
SCP_KNOWN_HOSTS_PATH = os.environ.get("SCP_KNOWN_HOSTS_PATH", "/secrets/ssh/known_hosts")

QUERY = """
    SELECT timestamp, reading
    FROM all_readings
    WHERE model = %s
      AND timestamp >= now() - (%s * interval '1 hour')
    ORDER BY timestamp ASC
"""

COLOR_MEAT = "#2a78d6"  # categorical slot 1 (blue)
COLOR_OUTDOOR = "#eb6834"  # categorical slot 2 (orange)
COLOR_WIND = "#1baf7a"  # categorical slot 3 (aqua)


def c_to_f(celsius):
    return celsius * 9 / 5 + 32


def kmh_to_mph(kmh):
    return kmh * 0.621371


def fetch_readings(model):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(QUERY, (model, LOOKBACK_HOURS))
            return cursor.fetchall()


def extract_series(rows, field, transform=lambda value: value):
    times = []
    values = []
    for timestamp, reading in rows:
        try:
            payload = json.loads(reading)
        except json.JSONDecodeError:
            continue

        if field not in payload:
            continue
        times.append(timestamp)
        values.append(transform(payload[field]))

    return times, values


def style_axis(ax):
    ax.set_facecolor("#fcfcfb")
    ax.grid(True, color="#e1e0d9", linewidth=0.8)
    ax.tick_params(colors="#898781")
    for spine_name, spine in ax.spines.items():
        if spine_name in ("top", "right"):
            spine.set_visible(False)
        else:
            spine.set_color("#c3c2b7")


def plot_panel(ax, title, times, values, color, value_fmt, min_value, max_value):
    ax.plot(times, values, color=color, linewidth=2, solid_capstyle="round")

    if times:
        latest_ts, latest_value = times[-1], values[-1]
        ax.scatter(
            [latest_ts], [latest_value],
            color=color, s=36, zorder=5,
            edgecolor="#fcfcfb", linewidth=1,
        )
        ax.text(
            0.99, 0.95, value_fmt.format(latest_value),
            transform=ax.transAxes, ha="right", va="top",
            fontsize=18, fontweight="bold", color="#0b0b0b",
        )
        latest_ts_eastern = latest_ts.replace(tzinfo=datetime.timezone.utc).astimezone(DISPLAY_TZ)
        ax.text(
            0.99, 0.80, f"as of {latest_ts_eastern:%Y-%m-%d %H:%M:%S %Z}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=8, color="#52514e",
        )
    else:
        ax.text(
            0.5, 0.5, "no data",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=10, color="#898781",
        )

    ax.set_title(title, color="#0b0b0b", fontsize=12, loc="left")
    ax.set_ylim(min_value, max_value)
    style_axis(ax)


def build_figure(meat, outdoor, wind):
    fig, (ax_meat, ax_outdoor, ax_wind) = plt.subplots(
        3, 1, figsize=(10, 11), dpi=150, sharex=True,
    )
    fig.patch.set_facecolor("#fcfcfb")

    plot_panel(
        ax_meat, f"{MAVERICK_MODEL} probe temperature", meat[0], meat[1],
        COLOR_MEAT, "{:.1f}°F", GRAPH_MIN_F, GRAPH_MAX_F,
    )
    ax_meat.set_ylabel("°F", color="#52514e")

    plot_panel(
        ax_outdoor, f"{ACURITE_MODEL} outdoor temperature", outdoor[0], outdoor[1],
        COLOR_OUTDOOR, "{:.1f}°F", OUTDOOR_MIN_F, OUTDOOR_MAX_F,
    )
    ax_outdoor.set_ylabel("°F", color="#52514e")

    plot_panel(
        ax_wind, f"{ACURITE_MODEL} wind speed", wind[0], wind[1],
        COLOR_WIND, "{:.1f} mph", WIND_MIN_MPH, WIND_MAX_MPH,
    )
    ax_wind.set_ylabel("mph", color="#52514e")
    ax_wind.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    fig.autofmt_xdate()
    fig.suptitle(f"Last {LOOKBACK_HOURS}h", color="#0b0b0b", fontsize=10, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
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
    maverick_rows = fetch_readings(MAVERICK_MODEL)
    acurite_rows = fetch_readings(ACURITE_MODEL)

    if not maverick_rows and not acurite_rows:
        print(
            f"no {MAVERICK_MODEL} or {ACURITE_MODEL} readings in the last {LOOKBACK_HOURS}h, "
            f"leaving previous graph at {OUTPUT_PATH} in place",
            flush=True,
        )
        return

    meat = extract_series(maverick_rows, "temperature_1_C", c_to_f)
    outdoor = extract_series(acurite_rows, "temperature_F")
    wind = extract_series(acurite_rows, "wind_avg_km_h", kmh_to_mph)

    fig = build_figure(meat, outdoor, wind)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())
    print(
        f"wrote {OUTPUT_PATH} from {len(maverick_rows)} {MAVERICK_MODEL} "
        f"and {len(acurite_rows)} {ACURITE_MODEL} readings",
        flush=True,
    )

    scp_graph()


if __name__ == "__main__":
    main()
