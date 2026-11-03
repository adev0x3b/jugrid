# Runbook

What to do when an alert arrives. Alarms and the failed-ingest rule are in
`infra/monitoring.tf` and publish to the `alerts_topic_arn` topic; each alert links its entry here.

The API logs one JSON line per request (`method`, `path`, `status`, `duration_ms`,
`request_id`) to the `/jugrid/api` log group, and every answer carries the same id in
`X-Request-Id`. In CloudWatch Logs Insights:

```
# Errors in the last hour, most frequent first
fields path, status | filter status >= 500 | stats count() by path | sort count() desc

# Slowest requests
fields @timestamp, path, duration_ms, request_id | sort duration_ms desc | limit 20

# Everything one request logged
fields @timestamp, level, message | filter request_id = "<id from X-Request-Id>"
```

## api-errors

The API answered 5 or more 5xx in 5 minutes.

1. Run the errors query above: one path or all of them?
2. All paths, with `OperationalError` in the logs: the database. Check `db-cpu`, the RDS
   console's connections, and whether the database is rebooting or in maintenance.
3. One path: open a failing request by its id and read the traceback.
4. Right after a deploy: the circuit breaker rolls back a deploy whose tasks fail their health
   check, but not one that answers 500 on some paths. Redeploy the previous image tag
   (`aws ecs update-service --task-definition <previous revision>`).

## api-down

No healthy API task for 2 minutes: the map shows no data.

1. ECS console, service `api`, Events tab: tasks failing to start (image pull, secrets) or
   failing the health check (`/api/health` runs `SELECT 1`).
2. Tasks start but fail the check: the database is unreachable, or the `jugrid_api` role is
   missing (the first ingest creates it: `terraform output run_ingest`).
3. Tasks do not start: `stoppedReason` in the Events tab; an image tag that does not exist in
   ECR is the usual one after a failed deploy.

## api-slow

The slowest 5% of answers took over 2 seconds for 15 minutes.

1. Slowest requests query: one path? `/api/grid/*` reads the Zarr store, the rest PostGIS.
2. Autoscaling adds tasks at 60% CPU up to `api_max_count`; check the service is at its cap.
3. CloudFront caches answers for 5 minutes, so a slow API under real load usually means
   requests that miss the cache: look for unusual query strings in the CloudFront logs.

## db-cpu

The database averaged over 80% CPU for 15 minutes.

1. During the monthly ingest (1st of the month, 03:00 UTC) this is expected for its scoring
   step; it clears when the ingest ends.
2. Otherwise: RDS Performance Insights, top SQL. A sequential scan on `assets` where the GiST
   index on `geom` should serve is the usual suspect.
3. Lasting load: a larger `db_instance_class`.

## db-storage

Under 2 GiB free.

1. Storage autoscaling is not set: raise `db_allocated_storage_gb` and apply (no downtime).
2. Check what grew: `assets` and `asset_risks` grow with OpenStreetMap; `ingest_runs` stays small.

## ingest-failed

The ingest task stopped with a non-zero exit code or did not start. A failed step rolls back
what it wrote to the database, so the map keeps the last good data; `/api/meta` lists the run
as failed.

1. The alert names the task; its log stream is in `/jugrid/ingest`. The last lines name the
   step (`assets`, `climate`, `score`) and the error.
2. Overpass answered 429 or 504: a busy public instance. Run the ingest again later
   (`terraform output run_ingest`), or point `JUGRID_OVERPASS_URL` at another instance.
3. A climate download failed: NASA's bucket is public and rarely down. Run the ingest again;
   on ECS its download cache is the task's temporary disk, so it starts the downloads over.
4. `TaskFailedToStart`: usually the image tag or the database secret; see `stoppedReason`.
