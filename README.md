# CTRM Trade Ingest & Audit Service

A containerized, cloud-native Commodity Trading and Risk Management (CTRM) microservice built with **FastAPI**, **PostgreSQL 15**, **GitHub Actions**, and **Kubernetes**. It ingests, validates, and durably persists physical and financial commodity trades with end-to-end `X-Correlation-ID` tracing and structured JSON audit logging.

> **Technical Report & Verification Evidence:** See [`REPORT.md`](./REPORT.md) for the full system architecture diagram, engineering trade-offs, failure/recovery verification, operational troubleshooting notes, and the 16-step evidence index in [`evidence/`](./evidence/).

---

## Key Features

- **Trade Validation & Persistence:** Strict Pydantic schema enforcement (`trade_id`, `commodity`, `volume`, `price`) backed by PostgreSQL 15.
- **Auditability & Observability:** Automatic `X-Correlation-ID` propagation across HTTP headers and structured JSON audit logs (`trade_ingested`).
- **Health & Readiness Probes:** Dedicated `/healthz` (liveness) and `/ready` (database connectivity) endpoints for zero-downtime Kubernetes orchestration.
- **Hardened Supply Chain & Runtime:** Multi-stage `python:3.11-slim-bookworm` build running as unprivileged user `appuser` (UID `10001`), gated by Ruff, Pytest, and Trivy (`CRITICAL`/`HIGH` blocking) in CI/CD before publishing immutable artifacts to GitHub Container Registry (`ghcr.io/virtualvance/ctrm-trade-ingest:v1.0.0`).
- **Resilient Kubernetes Deployment:** Multi-replica API deployment with a `wait-for-postgres` `initContainer` datastore readiness gate, `LoadBalancer` external routing (`localhost:8080`), and a 1Gi `PersistentVolumeClaim` (`postgres-data-pvc`) for datastore durability.

---

## API Endpoints

| Method | Endpoint | Description | Success Status |
| :--- | :--- | :--- | :--- |
| `GET` | `/healthz` | Liveness probe confirming the FastAPI/Uvicorn event loop is responsive | `200 OK` |
| `GET` | `/ready` | Readiness probe verifying active connectivity to PostgreSQL | `200 OK` |
| `POST` | `/trades` | Validates and persists a commodity trade record with audit logging | `201 Created` |
| `GET` | `/trades` | Retrieves all persisted commodity trade records | `200 OK` |
| `GET` | `/docs` | Interactive OpenAPI / Swagger UI documentation | `200 OK` |

---

## Repository Structure

```
ctrm-trade-ingest/
├── .github/workflows/ci.yml   # Lint, Pytest, Trivy scan, and GHCR publish pipeline
├── app/                       # FastAPI application, Pydantic models, and DB layer
├── k8s/                       # Modular Kubernetes manifests (01 through 05)
│   ├── 01-config-and-secret.yaml
│   ├── 02-postgres-pvc.yaml
│   ├── 03-postgres-deployment.yaml
│   ├── 04-app-deployment.yaml
│   └── 05-app-service.yaml
├── tests/                     # Pytest unit and API validation suite
├── evidence/                  # 16-step verification screenshots (local, CI/CD, K8s)
├── Dockerfile                 # Multi-stage, non-root production container image
├── LICENSE                    # Mozilla Public License 2.0 (MPL-2.0)
├── REPORT.md                  # Technical report, troubleshooting notes, and evidence index
└── README.md                  # Project overview, API contract, and quickstart guide
```

---

## Quickstart: Kubernetes Deployment

1. **Apply the manifests to your cluster:**
   ```powershell
   kubectl apply -f k8s/
   ```
2. **Verify pods, LoadBalancer service, and bound persistent volume:**
   ```powershell
   kubectl get all,pvc
   ```
3. **Access Swagger UI & submit a test trade:**
   Open `http://localhost:8080/docs` and execute `POST /trades`:
   ```json
   {
     "trade_id": "NG-JAN27-2001",
     "commodity": "Natural Gas",
     "volume": 100000,
     "price": 3.15
   }
   ```

---

## Quickstart: Local Development & Container Build

```powershell
# 1. Run unit and validation tests locally
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -v

# 2. Build the production multi-stage container image
docker build -t ctrm-trade-ingest:local .
```

---

## Author & Context

Developed by **Vance Reed** (Undergraduate in Software Development & Integration; M.S. student in Applied Artificial Intelligence at the **University of Oklahoma Polytechnic Institute (OUPI)**).

Created as an educational and engineering artifact for CI/CD DevOps at the University of Oklahoma Polytechnic Institute, demonstrating cloud-native microservice architecture, automated CI/CD security gating, and resilient Kubernetes orchestration for enterprise Commodity Trading and Risk Management (CTRM) workflows.

*Note: This software is an independent student work product and does not represent an official certification or endorsement by the University of Oklahoma.*

---

## License

This project is licensed under the **Mozilla Public License 2.0 (MPL-2.0)**. See the [`LICENSE`](./LICENSE) file for details.

Any modifications to existing source files must remain open-source under MPL-2.0, while allowing the service to be executed, combined, or integrated alongside external and proprietary enterprise workflows without viral copyleft constraints.