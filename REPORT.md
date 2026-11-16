# Technical Report: CTRM Trade Ingest & Audit Service

## 1. System Architecture & Pipeline Overview

The **CTRM Trade Ingest & Audit Service** is a containerized, cloud-native microservice designed to ingest, validate, and durably persist physical and financial commodity trade records with full audit correlation.

```text
[Developer Push / PR]
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ GitHub Actions CI/CD Pipeline (.github/workflows/ci.yml)          │
│  1. Lint & Unit Test (Ruff + Pytest)  ──► Fails fast on errors    │
│  2. Build & Vulnerability Scan (Trivy) ──► Blocks CRITICAL/HIGH   │
│  3. Publish Immutable Image (GHCR)     ──► ghcr.io/virtualvance/* │
└───────────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ Kubernetes Cluster (Docker Desktop / kind v1.36.1)                │
│                                                                   │
│  [External Client / Swagger UI]                                   │
│         │  http://localhost:8080                                  │
│         ▼                                                         │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Service: ctrm-api-service (LoadBalancer, Port 8080 -> 8000) │  │
│  └─────────────────────────────────────────────────────────────┘  │
│         │                                                         │
│         ├──────────────────────────┐                              │
│         ▼                          ▼                              │
│  ┌─────────────────────┐    ┌─────────────────────┐               │
│  │ Pod: api-replica-1  │    │ Pod: api-replica-2  │               │
│  │ (init: pg_isready)  │    │ (init: pg_isready)  │               │
│  └─────────────────────┘    └─────────────────────┘               │
│         │                          │                              │
│         └────────────┬─────────────┘                              │
│                      ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Service: postgres-service (ClusterIP, Port 5432)            │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                      │                                            │
│                      ▼                                            │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Pod: postgres-db (PostgreSQL 15 Alpine)                     │  │
│  │   └── Mounted Volume: postgres-data-pvc (1Gi, standard)     │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

- **Application Tier (`app/main.py`):** A FastAPI service running on Uvicorn that validates trade payloads via Pydantic, injects `X-Correlation-ID` headers across every request lifecycle, emits structured JSON audit logs (`trade_ingested`), and exposes dedicated `/healthz` (liveness) and `/ready` (database-backed readiness) probes.
- **CI/CD & Supply Chain Security (`.github/workflows/ci.yml`):** Automated pipeline enforcing Ruff static analysis, Pytest unit/integration checks, Trivy container vulnerability gating (`CRITICAL` and `HIGH` severity blocking), and immutable image tagging (`v1.0.0` + Git SHA) in GitHub Container Registry (GHCR).
- **Kubernetes Orchestration (`k8s/`):** Five modular manifests separating non-sensitive configuration (`01-config-and-secret.yaml`), durable storage (`02-postgres-pvc.yaml`), stateful database deployment (`03-postgres-deployment.yaml`), stateless multi-replica API deployment with init-container readiness gating (`04-app-deployment.yaml`), and external ingress (`05-app-service.yaml`).

---

## 2. Engineering Trade-Offs

- **Base Image & Multi-Stage Build (`Dockerfile`):** Used a pinned `python:3.11-slim-bookworm` multi-stage build to compile dependencies in an isolated builder stage and copy only the virtual environment into a minimal runtime image, reducing image footprint and minimizing CVE exposure.
- **Zero-Trust Non-Root Execution:** Enforced unprivileged container execution (`appuser`, UID `10001`, GID `10001`) in both the `Dockerfile` and the Kubernetes Pod `securityContext` (`runAsNonRoot: true`), adhering to the principle of least privilege.
- **External Ingress (`LoadBalancer` vs. `NodePort`):** Initially configured `k8s/05-app-service.yaml` as a `NodePort` (`30080`), which remained isolated inside Docker Desktop's `kind` container network. Switched `ctrm-api-service` to `type: LoadBalancer` (`8080:30080/TCP`), allowing Docker Desktop's ingress proxy to bind `localhost:8080` directly to the cluster without manual port-forwarding.
- **Datastore Readiness Gate (`initContainers`):** Added a `wait-for-postgres` `initContainer` (`pg_isready -h postgres-service -p 5432 -U postgres`) to `k8s/04-app-deployment.yaml`. This declaratively prevents API replicas from booting and executing schema initialization (`init_db()`) before PostgreSQL is ready to accept connections.
- **Persistent Storage & `Recreate` Strategy:** Configured a 1Gi `PersistentVolumeClaim` (`postgres-data-pvc` using the `standard` StorageClass) mounted at `/var/lib/postgresql/data` with `PGDATA` scoped to a subdirectory, paired with a `Recreate` deployment strategy so two database pods never contend for the same `ReadWriteOnce` volume.
- **Configuration & Secret Separation:** Decoupled non-sensitive parameters (`DB_HOST`, `DB_PORT`, `DB_NAME`) in `ConfigMap/ctrm-app-config` (`k8s/01-config-and-secret.yaml`) from database credentials (`Secret/ctrm-db-secret`), provisioning the Secret imperatively out-of-band via `kubectl create secret` so passwords are never committed to Git.

---

## 3. Failure & Recovery Verification

- **CI/CD Pipeline Failure Gate (`evidence/06-ci-fail-gate.png`):** Verified on branch `test-failure-gate` by intentionally asserting HTTP `500` instead of `200` on `/healthz`. Pytest failed immediately in the `lint-and-test` job, halting the pipeline and preventing unverified code from reaching Trivy vulnerability scanning or GHCR artifact publishing.
- **API Replica Self-Healing (`evidence/13-k8s-selfheal.png`):** Simulated an application tier outage by deleting both running `ctrm-trade-ingest` pods (`kubectl delete pod -l app=ctrm-trade-ingest`). The Kubernetes ReplicaSet controller immediately detected the state drift, scheduled two replacement pods, executed the `wait-for-postgres` init container on each, and restored `2/2` ready replicas within ~13 seconds.
- **Datastore Crash & Persistent Volume Recovery (`evidence/14-k8s-db-recovery.png`, `evidence/15-k8s-data-persisted.png`):** Destroyed the live PostgreSQL pod (`kubectl delete pod -l app=postgres-db`) while active trade records were stored. Kubernetes recreated `postgres-db` in `1/1 Running` status within 12 seconds and re-mounted `postgres-data-pvc`. Querying `GET /trades` via Swagger UI (`http://localhost:8080/docs`) confirmed HTTP `200` with previously ingested trades (`NG-JAN27-2001` and `CRUDE-FEB27-3005`) intact.

---

## 4. Operational Troubleshooting Observations

1. **Cold-Start Schema Race Condition (`relation "trades" does not exist`):**
   - **Observation:** Upon initial concurrent deployment (`kubectl apply -f k8s/`), the FastAPI replicas started milliseconds before PostgreSQL finished initializing `trades_db`. Because `init_db()` caught connection errors gracefully to avoid crash-looping, querying `GET /trades` initially returned HTTP `500` (`relation "trades" does not exist`).
   - **Resolution:** Added a `wait-for-postgres` `initContainer` to `k8s/04-app-deployment.yaml` using `pg_isready`. Subsequent rolling updates and pod restarts guaranteed PostgreSQL availability prior to FastAPI startup, eliminating the race condition.
2. **Structured Log Filtering Amid Health Probes (`evidence/12-k8s-logs.png`):**
   - **Observation:** Liveness (`/healthz`) and readiness (`/ready`) probes execute every 10–15 seconds across both API replicas, rapidly rotating default `kubectl logs` tail windows.
   - **Resolution:** Queried full pod log streams (`--tail=-1`) filtered by trade identifier or excluding probe endpoints (`Select-String -NotMatch "/healthz|/ready"`), isolating structured JSON audit events (`"event": "trade_ingested"`) complete with end-to-end `correlation_id` UUIDs.

---

## 5. Evidence Index

| Artifact | Description |
| :--- | :--- |
| [`evidence/01-local-health.png`](./evidence/01-local-health.png) | Local virtual environment health check and unit test verification |
| [`evidence/02-docker-build.png`](./evidence/02-docker-build.png) | Multi-stage Docker image build (`ctrm-trade-ingest`) |
| [`evidence/03-compose-up.png`](./evidence/03-compose-up.png) | Local Docker Compose multi-container stack startup |
| [`evidence/04-api-crud-test.png`](./evidence/04-api-crud-test.png) | Local `POST /trades` and `GET /trades` persistence verification |
| [`evidence/05-trivy-local.png`](./evidence/05-trivy-local.png) | Local Trivy container vulnerability scan (`0 CRITICAL/HIGH`) |
| [`evidence/06-ci-fail-gate.png`](./evidence/06-ci-fail-gate.png) | GitHub Actions pipeline blocking a failing Pytest assertion |
| [`evidence/07-ci-pass-pipeline.png`](./evidence/07-ci-pass-pipeline.png) | Green GitHub Actions CI/CD workflow (Lint, Test, Trivy, GHCR Push) |
| [`evidence/08-ghcr-package.png`](./evidence/08-ghcr-package.png) | Published immutable container image in GitHub Container Registry |
| [`evidence/09-cluster-ready.png`](./evidence/09-cluster-ready.png) | Docker Desktop Kubernetes (`v1.36.1`) node and `standard` StorageClass ready |
| [`evidence/10-k8s-deploy.png`](./evidence/10-k8s-deploy.png) | Active Kubernetes Deployments, Pods, Services, and Bound PVC |
| [`evidence/11-k8s-app-access.png`](./evidence/11-k8s-app-access.png) | Swagger UI (`http://localhost:8080/docs`) querying persisted trade `NG-JAN27-2001` |
| [`evidence/12-k8s-logs.png`](./evidence/12-k8s-logs.png) | Structured JSON `trade_ingested` audit log with `correlation_id` from Kubernetes pod |
| [`evidence/13-k8s-selfheal.png`](./evidence/13-k8s-selfheal.png) | ReplicaSet self-healing after deleting both `ctrm-trade-ingest` pods |
| [`evidence/14-k8s-db-recovery.png`](./evidence/14-k8s-db-recovery.png) | Automated `postgres-db` pod recovery after forced deletion |
| [`evidence/15-k8s-data-persisted.png`](./evidence/15-k8s-data-persisted.png) | Verification that trade records survived database pod destruction via PVC |
| [`evidence/16-final-repo.png`](./evidence/16-final-repo.png) | Final GitHub repository state with manifests, evidence, and technical report |