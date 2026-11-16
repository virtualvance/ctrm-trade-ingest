# CTRM Trade Ingest & Audit Service

A containerized, cloud-native Commodity Trading and Risk Management (CTRM) microservice built with **FastAPI**, **PostgreSQL 15**, **GitHub Actions**, and **Kubernetes**. It ingests, validates, and durably persists physical and financial commodity trades with end-to-end `X-Correlation-ID` tracing and structured JSON audit logging.

> **Technical Report & Verification Evidence:** See [`REPORT.md`](./REPORT.md) for the system architecture diagram, engineering trade-offs, failure/recovery verification, operational troubleshooting notes, and the 16-step evidence index in [`evidence/`](./evidence/).

---

## Prerequisites & Environment Versions

| Component | Verified Version / Configuration |
| :--- | :--- |
| **Runtime & Language** | Python `3.11+` (`python:3.11-slim-bookworm` in container) |
| **Container Engine** | Docker Desktop (with Buildx and Compose) |
| **Kubernetes Cluster** | Docker Desktop built-in `kind` cluster — **Kubernetes `v1.36.1`** |
| **CLI Tools** | `kubectl` (`v1.36+`), `git`, `trivy` (optional for local CVE scans) |

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
└── README.md                  # Project overview, API contract, and reproduction guide
```

---

## End-to-End Reproduction Guide (Clean Clone to Running Cluster)

### 1. Clone the Repository & Run Automated Tests
```powershell
git clone [https://github.com/virtualvance/ctrm-trade-ingest.git](https://github.com/virtualvance/ctrm-trade-ingest.git)
cd ctrm-trade-ingest

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -v
```

### 2. Obtain the Published Container Image (or Build Locally)
Pull the signed/verified production image published by GitHub Actions to GitHub Container Registry (GHCR):
```powershell
docker pull ghcr.io/virtualvance/ctrm-trade-ingest:v1.0.0
```
*(Optional)* Build locally from the multi-stage `Dockerfile`:
```powershell
docker build -t ctrm-trade-ingest:local .
```

### 3. Create the Kubernetes Secret Out-of-Band (Without Committing Real Credentials)
Before deploying, create or override `ctrm-db-secret` imperatively in your local cluster so real production passwords are never committed to version control:
```powershell
kubectl create secret generic ctrm-db-secret `
  --from-literal=DB_USER=postgres `
  --from-literal=DB_PASSWORD='<YOUR_STRONG_LOCAL_PASSWORD>' `
  --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Deploy Kubernetes Manifests
Apply the ConfigMap, `PersistentVolumeClaim`, PostgreSQL deployment, multi-replica API deployment (`initContainer` gated), and `LoadBalancer` service:
```powershell
kubectl apply -f k8s/
```

### 5. Verify Rollout Status, Pods, Services, and PVCs
Confirm both deployments finish rolling out cleanly and the `1Gi` volume is `Bound`:
```powershell
kubectl rollout status deployment/postgres-db
kubectl rollout status deployment/ctrm-trade-ingest
kubectl get pods,svc,pvc
```
Expected state:
- `pod/postgres-db-*` (`1/1 Running`) and two `pod/ctrm-trade-ingest-*` replicas (`1/1 Running`).
- `service/ctrm-api-service` (`TYPE: LoadBalancer`, `PORT(S): 8080:30080/TCP`).
- `persistentvolumeclaim/postgres-data-pvc` (`STATUS: Bound`, `CAPACITY: 1Gi`).

### 6. Access & Test the Application from the Host
Docker Desktop's `LoadBalancer` ingress maps `localhost:8080` directly to the API service:
- **Interactive Swagger UI:** Open `http://localhost:8080/docs` in your browser.
- **Health & Readiness Endpoints:**
  - `GET http://localhost:8080/healthz` $\rightarrow$ `200 OK`
  - `GET http://localhost:8080/ready` $\rightarrow$ `200 OK`
- **Ingest & Query a Trade via CLI:**
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8080/trades" -Method Post -ContentType "application/json" -Body '{"trade_id":"NG-JAN27-2001","commodity":"Natural Gas","volume":100000,"price":3.15}'
  Invoke-RestMethod -Uri "http://localhost:8080/trades" -Method Get
  ```
- **Inspect Structured Audit Logs:**
  ```powershell
  kubectl logs -l app=ctrm-trade-ingest --tail=-1 | Select-String "trade_ingested"
  ```

### 7. Clean Up / Tear Down Cluster Resources
Remove all deployed Kubernetes resources and release the persistent volume claim when finished:
```powershell
kubectl delete -f k8s/
```
*(If resetting the entire Docker Desktop Kubernetes cluster, open **Docker Desktop $\rightarrow$ Settings $\rightarrow$ Kubernetes $\rightarrow$ Reset Kubernetes Cluster**.)*

---

## API Contract Summary

| Method | Endpoint | Description | Success Status |
| :--- | :--- | :--- | :--- |
| `GET` | `/healthz` | Liveness probe confirming the FastAPI/Uvicorn event loop is responsive | `200 OK` |
| `GET` | `/ready` | Readiness probe verifying active connectivity to PostgreSQL | `200 OK` |
| `POST` | `/trades` | Validates and persists a commodity trade record with audit logging | `201 Created` |
| `GET` | `/trades` | Retrieves all persisted commodity trade records | `200 OK` |
| `GET` | `/docs` | Interactive OpenAPI / Swagger UI documentation | `200 OK` |

---

## Author & Context

Developed by **Vance Reed** (Undergraduate in Software Development & Integration; M.S. student in Applied Artificial Intelligence at the **University of Oklahoma Polytechnic Institute (OUPI)**).

Created as an educational and engineering artifact for DevOps – CI/CD at the University of Oklahoma Polytechnic Institute, demonstrating cloud-native microservice architecture, automated CI/CD security gating, and resilient Kubernetes orchestration for enterprise Commodity Trading and Risk Management (CTRM) workflows.

*Note: This software is an independent student work product and does not represent an official certification or endorsement by the University of Oklahoma.*

---

## License

This project is licensed under the **Mozilla Public License 2.0 (MPL-2.0)**. See the [`LICENSE`](./LICENSE) file for details.

Any modifications to existing source files must remain open-source under MPL-2.0, while allowing the service to be executed, combined, or integrated alongside external and proprietary enterprise workflows without viral copyleft constraints.