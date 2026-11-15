# Technical Report: CTRM Trade Ingest & Audit Service

## 1. System Architecture & Pipeline Overview
*(Architecture diagram and workflow summary will be added here upon completion)*

## 2. Engineering Trade-Offs
* **Base Image & Multi-Stage Build:** Used a pinned `python:3.11-slim-bookworm` multi-stage build to compile dependencies in an isolated builder stage and copy only the virtual environment to a minimal runtime image, reducing image size and attack surface.
* **Security & Non-Root Execution:** Configured an unprivileged system user (`appuser`, UID 10001) inside the container runtime to adhere to the principle of least privilege.
* **Persistent Storage:** Configured a Kubernetes `PersistentVolumeClaim` (`postgres-pvc`) mounted to `/var/lib/postgresql/data` so commodity trade records survive database pod restarts or rescheduling.
* **Secret Management:** Separated non-sensitive configuration (`ConfigMap`) from database credentials (`Secret`), tracking only `k8s/secret-template.yaml` in Git while creating the live secret out-of-band locally.

## 3. Failure & Recovery Verification
* **CI/CD Pipeline Gate (`06-ci-fail-gate.png`):** *(To be documented in Phase 4)*
* **Application Availability & Self-Healing (`14-zero-downtime.png`, `15-self-healing.png`):** *(To be documented in Phase 5)*
* **Datastore Persistence Recovery (`16-data-persistence.png`):** *(To be documented in Phase 5)*

## 4. Operational Troubleshooting Observation
* *(To be documented in Phase 5 from `kubectl logs`, `kubectl describe`, or `kubectl top`)*