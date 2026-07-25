# kubernetes-meat-thermometer-graph

Kubernetes CronJob that graphs Maverick ET-73 meat thermometer temperature over
the last 8 hours and publishes it as a PNG.

## What it does

`graph_maverick.py` queries the `sdr433` Postgres database's `all_readings`
table for `Maverick-ET73` rows from the last `LOOKBACK_HOURS` (default 8),
converts each probe's Celsius reading to Fahrenheit, and renders a line chart
(Probe 1 / Probe 2) to `OUTPUT_PATH` (default `/output/maverick-temperature.png`).
If no readings are found in the window, the previous PNG is left in place
rather than overwritten.

## Pieces

- `graph_maverick.py` / `Dockerfile` / `requirements.txt` — the job itself.
- `k8s/pvc.yaml` — `meat-thermometer-graph-pvc`, where the CronJob writes the PNG.
- `k8s/graph-cronjob.yaml` — runs the job every 10 minutes, reading DB
  credentials from the existing `sdr433-role-credentials` secret (same one
  used by `kubernetes-mosquito`).
- `k8s/graph-server-deployment.yaml` — a small `nginx:alpine` deployment +
  NodePort service (`:30002`) that serves the PVC's contents, since no static
  file server already existed in the cluster to publish the image from.
- `Jenkinsfile` — builds/pushes the image to `kregistry.siwko.org:5000` and
  applies the manifests above, following the same pattern as
  `kubernetes-mosquito`.

## Configuration (env vars on the CronJob container)

| Var                                  | Default                                                            |
| ------------------------------------ | ------------------------------------------------------------------ |
| `PGHOST` / `PGPORT` / `PGDATABASE`   | `prod-postgres-rw.default.svc.cluster.local` / `5432` / `sdr433`   |
| `PGUSER` / `PGPASSWORD`              | from `sdr433-role-credentials` secret                              |
| `MAVERICK_MODEL`                     | `Maverick-ET73`                                                    |
| `LOOKBACK_HOURS`                     | `8`                                                                |
| `OUTPUT_PATH`                        | `/output/maverick-temperature.png`                                 |

## Viewing the graph

Once deployed, the PNG is available at `http://<any-node-ip>:30002/maverick-temperature.png`.
