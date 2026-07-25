# kubernetes-meat-thermometer-graph

Kubernetes CronJob that graphs Maverick ET-73 meat thermometer temperature,
plus outdoor temperature and wind speed from an Acurite-5n1 weather station,
over the last 8 hours and publishes it as a PNG.

## What it does

`graph_maverick.py` queries the `sdr433` Postgres database's `all_readings`
table for `Maverick-ET73` and `Acurite-5n1` rows from the last `LOOKBACK_HOURS`
(default 8) and renders three stacked panels sharing a time axis — meat probe
temperature, outdoor temperature, and wind speed — each with its own y-axis
range, since the three measurements are different quantities on different
scales (mixing them onto one shared axis would misrepresent the data):

- **Meat probe temperature** — probe 1's Celsius reading converted to
  Fahrenheit, fixed `GRAPH_MIN_F`–`GRAPH_MAX_F` (default 0–250), plus
  `MAVERICK_OFFSET_F` (default 0) added on top to correct for sensor drift. The
  probe currently reads 41°F high, so this is set to `-41` in
  `k8s/graph-cronjob.yaml`. When `MAVERICK_RECALIBRATED_AT` (an ISO 8601
  timestamp) is set, the panel shows a small note recording when the
  correction was applied and its size, converted to America/New_York for
  display.
- **Outdoor temperature** — Acurite-5n1's `temperature_F` field (already
  Fahrenheit), fixed `OUTDOOR_MIN_F`–`OUTDOOR_MAX_F` (default -20–120).
- **Wind speed** — Acurite-5n1's `wind_avg_km_h` field converted to mph, fixed
  `WIND_MIN_MPH`–`WIND_MAX_MPH` (default 0–40).

Each panel calls out its most recent reading directly on the chart with an
"as of" timestamp, converted from the database's UTC storage to
America/New_York (matching the convention in
`kubernetes-mosquito/update_reading_age.py`). The PNG is written to
`OUTPUT_PATH` (default `/output/maverick-temperature.png`). If neither sensor
has readings in the window, the previous PNG is left in place rather than
overwritten; if only one does, that panel still renders and the other shows
"no data".

After a successful write, the PNG is also `scp`'d to `lts.siwko.org:/var/www/html/maverick-temperature.png`.

## Pieces

- `graph_maverick.py` / `Dockerfile` / `requirements.txt` — the job itself.
- `k8s/pvc.yaml` — `meat-thermometer-graph-pvc`, where the CronJob writes the PNG.
- `k8s/graph-cronjob.yaml` — runs the job every minute, reading DB credentials
  from the existing `sdr433-role-credentials` secret (same one used by
  `kubernetes-mosquito`), and an SSH key from `meat-thermometer-graph-ssh-key`
  for the scp step.
- `k8s/ssh-known-hosts-configmap.yaml` — pins `lts.siwko.org`'s SSH host key
  (fetched via `ssh-keyscan -p 8022 lts.siwko.org`) so scp isn't exposed to a
  MITM on first connect.
- `k8s/graph-server-deployment.yaml` — a small `nginx:alpine` deployment +
  NodePort service (`:30002`) that serves the PVC's contents, since no static
  file server already existed in the cluster to publish the image from. This
  is now a secondary/backup view — `lts.siwko.org` is the primary published copy.
- `Jenkinsfile` — builds/pushes the image to `kregistry.siwko.org:5000` and
  applies the manifests above, following the same pattern as
  `kubernetes-mosquito`.

## SSH key for scp to lts.siwko.org

`meat-thermometer-graph-ssh-key` is a dedicated ed25519 keypair, scoped only to
this job (not the `ansible` repo's automation keys). It's created directly in
the cluster rather than committed to git:

```bash
kubectl create secret generic meat-thermometer-graph-ssh-key -n default \
  --from-file=id_ed25519=<private-key-path>
```

The matching public key must be added to `root`'s `~/.ssh/authorized_keys` on
`lts.siwko.org`:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBYUOl+RKKpNMK7POCXHEg2k1HCOKnIdO9VMbnu5PcIE meat-thermometer-graph-cronjob@k8s
```

If the secret is ever lost, generate a new pair, recreate the secret, and swap
in the new public key on `lts.siwko.org`.

## Configuration (env vars on the CronJob container)

| Var | Default |
| --- | --- |
| `PGHOST` / `PGPORT` / `PGDATABASE` | `prod-postgres-rw.default.svc.cluster.local` / `5432` / `sdr433` |
| `PGUSER` / `PGPASSWORD` | from `sdr433-role-credentials` secret |
| `MAVERICK_MODEL` / `ACURITE_MODEL` | `Maverick-ET73` / `Acurite-5n1` |
| `LOOKBACK_HOURS` | `8` |
| `GRAPH_MIN_F` / `GRAPH_MAX_F` | `0` / `250` |
| `MAVERICK_OFFSET_F` | `0` (`-41` in the deployed manifest) |
| `MAVERICK_RECALIBRATED_AT` | unset (ISO 8601 timestamp, e.g. `2026-07-25T16:14:38+00:00`) |
| `OUTDOOR_MIN_F` / `OUTDOOR_MAX_F` | `-20` / `120` |
| `WIND_MIN_MPH` / `WIND_MAX_MPH` | `0` / `40` |
| `OUTPUT_PATH` | `/output/maverick-temperature.png` |
| `SCP_HOST` / `SCP_PORT` / `SCP_USER` | `lts.siwko.org` / `8022` / `root` |
| `SCP_PATH` | `/var/www/html/maverick-temperature.png` |
| `SCP_KEY_PATH` / `SCP_KNOWN_HOSTS_PATH` | `/secrets/ssh/id_ed25519` / `/secrets/ssh/known_hosts` |

## Viewing the graph

- Primary: `https://lts.siwko.org/maverick-temperature.png`
- Backup (served straight from the PVC): `http://<any-node-ip>:30002/maverick-temperature.png`
