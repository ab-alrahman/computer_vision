# Smart Toll Road — Build TODO

> Master checklist. Work top-to-bottom **per phase**, but run **Track A (Data/AI)** in parallel from day 1.
> Legend: `[ ]` todo · `[x]` done · `[P0]` blocking · `[P1]` important · `[P2]` bonus/optional · `→` depends on

---

## How to use

- One checkbox = one PR (or one commit if tiny).
- A task is **Done** only when it satisfies the **Definition of Done** (bottom of this file).
- Do not start a phase before the previous phase's exit criteria are met.
- Update this file in the same PR that completes a task.

---

## Decisions to lock (before any code)

- [ ] `[P0]` ORM for the API: **Drizzle** or TypeORM?
- [ ] `[P0]` API style: REST only, or REST + WebSocket? (recommend both, WS for realtime)
- [ ] `[P0]` Mobile: **Expo** or bare React Native? (affects push setup)
- [ ] `[P0]` Primary DB: managed (Supabase / RDS) or local Docker only for dev?
- [ ] `[P1]` Realtime video needed in the app? (MJPEG vs snapshot-only) → decides scope
- [ ] `[P1]` Broker: plain HTTP ingest now, or Redis/Kafka from day 1? (recommend HTTP now)
- [ ] `[P1]` Object storage for violation snapshots / annotated video: MinIO (self-hosted) or S3?
- [ ] `[P1]` Auth: JWT access + refresh, roles `ADMIN/OPERATOR/POLICE/VIEWER` — confirm
- [ ] `[P2]` Single site or multi-site from day 1? (schema supports multi-site either way)
- [ ] `[P2]` Language: Arabic only, or `ar` + `en` i18n from the start?

> Write each answer into `docs/decisions/ADR-XXX.md` later. Do not re-litigate decided items.

---

## Track B — System Backbone

### Phase 0 — Foundation (2 days)

**Repo & tooling**
- [ ] `[P0]` Create monorepo structure (see `docs/system_design.md` §9) or 3 separate repos
- [ ] `[P0]` `git init`, `.gitignore` (py, node, .env, datasets/, runs/, *.onnx)
- [ ] `[P0]` Branching: `main` (protected) / `develop` / `feat/*` / `fix/*`
- [ ] `[P0]` Conventional Commits + commit hooks
- [ ] `[P0]` Root `README.md` (what/why/how-to-run skeleton)

**Containers**
- [ ] `[P0]` `docker-compose.yml`: `postgres:16` + `adminer` (UI)
- [ ] `[P0]` `docker-compose.dev.yml`: `redis:7` (later, optional)
- [ ] `[P0]` `.env.example` with every required var
- [ ] `[P0]` Verify `docker compose up -d` → postgres healthy → Adminer reachable

**Python env**
- [ ] `[P0]` Python 3.10/3.11 + `venv`
- [ ] `[P0]` `requirements.txt` pinned: `ultralytics`, `opencv-python`, `numpy`, `onnxruntime`, `lap`, `pandas`
- [ ] `[P0]` `pyproject.toml` or `setup.cfg` with `ruff` + `pytest` config
- [ ] `[P0]` Smoke test: open the video, read 1 frame, print shape

**CI**
- [ ] `[P0]` GitHub Actions: `lint` (ruff + eslint) → green
- [ ] `[P1]` GitHub Actions: `test` (pytest + jest)
- [ ] `[P1]` GitHub Actions: `build` (docker image)

**Exit criteria:** fresh clone → `docker compose up` + `pytest` + `npm test` all pass locally and in CI.

---

### Phase 1 — Contracts ⛔ BLOCKS EVERYTHING (3 days)

> No feature code until this phase is done. This is the highest-leverage 3 days of the project.

- [ ] `[P0]` Write `contracts/openapi.yaml` (v1) covering:
  - [ ] `[P0]` Auth: `login`, `refresh`, `logout`, `me`
  - [ ] `[P0]` Sites + Sides
  - [ ] `[P0]` Sessions: create, list, get, stop
  - [ ] `[P0]` Ingest: `POST /ingest/sessions/{id}/batch`, `POST /ingest/sessions/{id}/heartbeat`
  - [ ] `[P0]` Events / Tracks / Violations (paginated queries)
  - [ ] `[P0]` Alerts: list, get, ack
  - [ ] `[P0]` Report: `GET /sessions/{id}/report?format=`
  - [ ] `[P0]` Config: `bundle`, `tolls`, `speed-limits`, `lines`, `classes`
  - [ ] `[P1]` Health: `/healthz`, `/metrics`
- [ ] `[P0]` `contracts/event.schema.json` — the unified event envelope
  - [ ] `[P0]` Enum types: `EventType`, `ClassCode`, `Direction`, `SideCode`, `AlertStatus`, `Role`
  - [ ] `[P0]` `eventId` documented as the **idempotency key**
- [ ] `[P0]` SQL schema draft (see `docs/api_contract.md` §9) → Drizzle schema file
  - [ ] `[P0]` First migration applied and reversible
- [ ] `[P0]` Generate TS types for the mobile app from `openapi.yaml` (e.g. `openapi-typescript`)
- [ ] `[P0]` Generate Python dataclasses / Pydantic models from `event.schema.json`
- [ ] `[P1]` Mock server serving the contract (Swagger UI + fake data) so mobile can start
- [ ] `[P1]` Contract tests: schema validation of sample payloads

**Exit criteria:** `openapi.yaml` reviewed by the whole team; both Python and mobile devs can code against it with zero questions.

---

### Phase 2 — API Backbone (1 week)

**Scaffold**
- [ ] `[P0]` NestJS app with module folders matching the contract
- [ ] `[P0]` Drizzle wired to Postgres, migrations run in CI
- [ ] `[P0]` Config module loading `.env` with validation

**Auth & RBAC**
- [ ] `[P0]` `auth`: login, refresh, logout, `me`
- [ ] `[P0]` Password hashing (argon2 or bcrypt)
- [ ] `[P0]` Guards: `JwtAuthGuard`, `RolesGuard`
- [ ] `[P1]` `audit_log` written on every mutating request
- [ ] `[P1]` Seed script: admin user + demo site + 2 sides

**Core modules**
- [ ] `[P0]` `sites` + `sides` CRUD
- [ ] `[P0]` `devices` CRUD + API key issuance (store **hash**, never plaintext)
- [ ] `[P0]` `sessions`: create / list / get / stop
- [ ] `[P0]` `ingest`: batch endpoint
  - [ ] `[P0]` Validate payload against `event.schema.json`
  - [ ] `[P0]` **Idempotency**: `ON CONFLICT (id) DO NOTHING` on `events.id`
  - [ ] `[P0]` Return `{ accepted, duplicates, alertsCreated }`
  - [ ] `[P0]` Rate limiting (429 + `Retry-After`)
- [ ] `[P0]` `events`, `tracks`, `violations` read endpoints with pagination + filters
- [ ] `[P0]` `reports`: build the direction × class matrix + revenue from `events`
  - [ ] `[P0]` Unit tests for the aggregation logic
- [ ] `[P0]` `config` module: tolls, speed limits, counting lines, class colors
  - [ ] `[P0]` Every write bumps `configVersion`
- [ ] `[P1]` Global exception filter → `{ error: { code, message, details, traceId } }`
- [ ] `[P1]` `/healthz` + `/metrics` (Prometheus)
- [ ] `[P1]` Unit + integration tests (Supertest against test DB)

**Exit criteria ✅ Vertical Slice #1:**
`curl` a fake batch of 10 events → `GET /sessions/{id}/report` returns a correct matrix and revenue total. No Python involved.

---

### Phase 3 — Vision Service happy path (1 week)

**Source & preprocessing**
- [ ] `[P0]` `source.py`: video reader in a thread + frame queue + FPS meter
- [ ] `[P0]` `scripts/cut_video.py`: extract 04:00 → 09:00 into `data/raw/`
- [x] `[P1]` `preprocess.py`: denoise + CLAHE, switchable per config — done as `enhance.py` (`bilateral → CLAHE → unsharp`), toggled by `enhancement.enabled`
- [ ] `[P1]` Auto light/night profile selection from mean brightness

**Detector**
- [ ] `[P0]` `detector.py` with YOLO11n pretrained, COCO classes only
- [ ] `[P0]` Config: `conf` threshold, `imgsz`
- [ ] `[P1]` Inference benchmark: FPS on 8 CPU, record the number

**Tracker**
- [ ] `[P0]` `tracker.py` with pluggable backends behind one interface
  - [ ] `[P0]` `centroid` (baseline / MVP)
  - [ ] `[P0]` `iou`
  - [ ] `[P1]` `sort` (Kalman + IoU)
  - [ ] `[P1]` `bytetrack` ← required to hit the 85% occlusion target
- [ ] `[P0]` Track lifecycle: `birth` / `confirm(min_hits)` / `death(max_age)`
- [ ] `[P1]` ID-switch counter exposed as a metric

**Counting & rules**
- [ ] `[P0]` `geometry.py`: counting line per direction + polygon zones
- [ ] `[P0]` Direction inference (OUTBOUND / INBOUND)
- [ ] `[P0]` `counted` flag per track → **no double counting**
- [x] `[P0]` Deadband around the line (hysteresis) to survive stops on the line — `deadband_px`, set to 12
- [ ] `[P0]` `rules.py`: toll table → `PASSAGE` events with `amount`
- [ ] `[P0]` `annotator.py`: per-class colors, HUD with live counters

**Ingest client**
- [ ] `[P0]` `ingest_client.py`: batch events every 1s (or on N events)
- [ ] `[P0]` Local disk queue when the API is unreachable
- [ ] `[P0]` Retry with backoff; resume from queue on reconnect
- [ ] `[P0]` Write events to `output.mp4` with boxes drawn

**Exit criteria ✅ Vertical Slice #2:**
Run on the 04:00–09:00 clip → correct two-way counts → events land in Postgres → the NestJS report shows a real matrix. **This is the first full end-to-end system.**

---

### Phase 4 — Speed & Violations (4 days)

- [ ] `[P0]` `scripts/calibrate_geometry.py`: pick 4 ground-plane reference points, compute homography
- [ ] `[P0]` `velocity.py`: project centroid to BEV → meters → m/s → km/h
- [ ] `[P0]` Smoothing: EMA (α≈0.3) or 1D Kalman
- [ ] `[P0]` Speed limit `X` from config, with hysteresis to avoid flapping
- [ ] `[P0]` `SPEED_VIOLATION` event with measured + limit values
- [ ] `[P0]` **Red is reserved for violations only** — verify class colors never use red
- [ ] `[P0]` `MOTORCYCLE_VIOLATION` for non-police motorcycles
- [ ] `[P0]` `approachFrom` (LEFT/RIGHT/NORTH/SOUTH) derived from motion vector
- [ ] `[P0]` Server-side alert creation on motorcycle violation
- [ ] `[P0]` Alert message template: `"انتبه مرور مخالف قادم إليك - {approachFrom}"`
- [ ] `[P0]` `POST /alerts/{id}/ack` flow works end-to-end
- [ ] `[P1]` ETA calculation (`etaSeconds`) from speed + distance
- [ ] `[P1]` Violation snapshot: crop the frame and upload to object storage
- [ ] `[P1]` WebSocket gateway: `alert.created` fan-out per side

**Exit criteria:** speeding vehicle gets a red box + logged event; motorcycle violation produces a targeted alert that can be acknowledged.

---

## Track A — Data & Fine-tuning ⏰ LONGEST POLE, START DAY 1

> Runs **in parallel** with Phase 0–4 using the pretrained model. Blocks nothing until Phase 7.

### A1 — Audit the test video (1 day)
- [ ] `[P0]` `scripts/audit_video.py`: run pretrained YOLO11n on the whole clip
- [ ] `[P0]` Report counts per class per direction
- [ ] `[P0]` **Answer:** does the clip actually contain vans? police motorcycles?
- [ ] `[P0]` If no police motorcycles exist in the clip → raise with instructors, document limitation

### A2 — Acquire `van` (1 week)
- [ ] `[P0]` `scripts/fetch_openimages.py`: download Open Images images for the `Van` class
  - [ ] `[P0]` Look up the `Van` MID id in `class-descriptions-boxable.csv`
  - [ ] `[P0]` Bounding-box annotations CSV (train split)
  - [ ] `[P0]` Download with threads; cap at ~2000 images
  - [ ] `[P0]` Convert to YOLO labels (Open Images coords are already normalized 0–1)
  - [ ] `[P0]` Drop non-target classes and images containing only non-target classes
  - [ ] `[P0]` Record the Open Images license (CC BY 2.0) for the report
- [ ] `[P1]` Add `UA-DETRAC` (has a real `van` class, traffic domain)
- [ ] `[P1]` Add generic traffic scenes from Roboflow Universe / Kaggle
- [ ] `[P0]` Collect **hard negatives**: small trucks/buses that must NOT be labeled `van`

### A3 — Acquire `traffic-police motorcycle` (1–2 weeks)
- [ ] `[P0]` Web image search: "traffic police motorcycle", "motorcycle police", "دورية مرور"
- [ ] `[P0]` Collect 200–400 candidate images
- [ ] `[P1]` Extract frames from public dashcam / traffic-police videos
- [ ] `[P0]` **Fallback plan (B):** two-stage — YOLO11n detects `motorcycle` (COCO class), then a small binary CNN head classifies `police` vs `not-police`
  - [ ] `[P1]` Decide: single 6-class model vs 5-class + attribute head (write an ADR)

### A4 — Annotate (1 week)
- [ ] `[P0]` Tool: LabelImg / Label Studio / CVAT
- [ ] `[P0]` Label all van + police-moto samples
- [ ] `[P0]` QA pass: 100 random labels reviewed by a second person
- [ ] `[P0]` `scripts/merge_dataset.py`: merge OI + web + self-collected
- [ ] `[P0]` Split **by source, not by frame** (avoid leakage from near-duplicate frames)
  - [ ] `[P0]` 80/20 train/val
  - [ ] `[P0]` Validate: no near-duplicate image hashes across splits
- [ ] `[P0]` `data.yaml` with 6 classes in fixed order
  - [ ] `[P0]` Freeze the class order and record it in the report

### A5 — Train (1 week, GPU)
- [ ] `[P0]` Train on Colab/Kaggle free GPU (**inference stays on CPU** per the spec)
- [ ] `[P0]` Start from `yolo11n.pt` pretrained
- [ ] `[P0]` Hyperparameters: `imgsz=640`, `epochs≈80`, `batch=16`, `freeze=10` first
- [ ] `[P0]` Save the run: `runs/toll6/weights/best.pt` → `models/yolo11n-toll.pt`
- [ ] `[P0]` Evaluate: per-class mAP50 + confusion matrix
- [ ] `[P0]` **Targets:** Recall(`van`) ≥ 0.80, Recall(`police-moto`) ≥ 0.70
- [ ] `[P0]` Verify confusion pairs shrank: `bus↔van`, `motorcycle↔police-moto`
- [ ] `[P0]` Record the exact hyperparameters + hardware + wall time for the report

### A6 — Optimize & swap (2 days)
- [ ] `[P0]` `model.export(format="onnx", int8=True)`
- [ ] `[P0]` `detector.py` supports the ONNX backend behind the same interface
- [ ] `[P0]` Re-benchmark FPS with int8 vs fp32
- [ ] `[P0]` Re-run the audit video and compare against the pretrained baseline
- [ ] `[P1]` If recall is short, do a second fine-tune round on the failing classes

---

### Phase 6 — Police App (2–3 weeks, unblocked after Phase 1)

- [ ] `[P0]` Expo/React Native project, app name + bundle id
- [ ] `[P0]` API client generated from the contract
- [ ] `[P0]` Auth: login, JWT storage in secure storage, refresh flow
- [ ] `[P0]` Home: unread alerts badge + list
- [ ] `[P0]` Alerts list with status filter (PENDING / ACKED)
- [ ] `[P0]` Alert detail: photo/snapshot, message, time, **big ACK button**
- [ ] `[P0]` ACK → `POST /alerts/{id}/ack` → optimistic UI update
- [ ] `[P0]` Reports screen: direction × class matrix + revenue
- [ ] `[P1]` Push: FCM/APNs setup + token registration endpoint
- [ ] `[P1]` Local notification on `alert.created`
- [ ] `[P1]` Offline read cache (`react-query` + AsyncStorage)
- [ ] `[P2]` Live view: MJPEG stream + bounding boxes from `ws /sessions/{id}/boxes`
- [ ] `[P2]` WebSocket reconnect using `?sinceSeq=`
- [ ] `[P2]` Arabic/English language switch

**Exit criteria:** a police officer can log in on a phone, receive a motorcycle alert with a push notification, acknowledge it, and view the session report.

---

### Phase 7 — Evaluation & Hardening (1 week)

- [ ] `[P0]` Build `ground_truth.csv` (hand-labelled, ~100 passages: class, direction, times)
- [ ] `[P0]` `scripts/eval.py`:
  - [ ] `[P0]` Count accuracy per class × direction
  - [ ] `[P0]` ID switches
  - [ ] `[P0]` Occlusion robustness — **must be ≥ 85%**
  - [ ] `[P0]` False-positive alert rate
  - [ ] `[P0]` FPS on 8 CPU, no GPU
- [ ] `[P0]` Performance tuning pass:
  - [ ] `[P1]` `imgsz` sweep (640 / 512 / 352)
  - [ ] `[P1]` `torch.set_num_threads`, `cv2.setNumThreads`, ORT `intra_op`
  - [ ] `[P1]` Frame reader thread + queue sizing
- [ ] `[P1]` Lighting/weather robustness: darken the clip, simulate rain, re-run eval
- [ ] `[P1]` Fail-safe: if the API dies mid-session, the video pipeline must not stop
- [ ] `[P2]` Annotated video output + violation snapshot storage

---

### Phase 8 — Delivery (3 days)

- [ ] `[P0]` README: architecture, how to run everything, screenshots
- [ ] `[P0]` Architecture diagram (the mermaid diagrams in `docs/system_design.md`)
- [ ] `[P0]` ADRs: tracker choice, speed calibration, fine-tuning strategy, broadcast choice
- [ ] `[P0]` **Rubric mapping** (from the spec):
  - [ ] `[P0]` Detection & counting accuracy → link to eval results
  - [ ] `[P0]` Processing speed (FPS) → link to benchmark
  - [ ] `[P0]` Documentation quality → this README + docs/
- [ ] `[P0]` Assumptions & limitations section (honest: training data overlap, test clip limitations)
- [ ] `[P1]` Seed data + demo script so a reviewer can run the whole system in 5 minutes
- [ ] `[P1]` Demo video (3–5 min): violation alert on the phone + final report

---

## Definition of Done (every task)

- [ ] Code reviewed and merged to `develop`
- [ ] At least one test for new logic (pytest / jest)
- [ ] Lint + typecheck pass locally and in CI
- [ ] `openapi.yaml` updated if any endpoint changed
- [ ] DB migration added if schema changed (and reversible)
- [ ] README / docs updated if behavior changed
- [ ] Checkbox ticked in this file, in the same PR

---

## Definition of Ready (before starting a task)

- [ ] The phase's exit criteria from the previous phase are met
- [ ] The task is small enough for one PR (< 300 lines)
- [ ] Acceptance criteria are written (what proves it works?)
- [ ] Any contract/DB change agreed in the weekly sync

---

## Weekly ritual

- [ ] Monday: pick tasks for the week, update the board
- [ ] Thursday: 10-minute demo on `develop` — no "almost done" allowed
- [ ] Friday: update this TODO, write the weekly log entry, tag blockers
- [ ] Any contract change → version bump + notify the whole team the same day

---

## Risk watchlist

- [ ] `[!]` Fine-tuning slips → it is the longest pole; slip here slips the whole project
- [ ] `[!]` `van` never appears in the test clip → cannot be evaluated; raise early
- [ ] `[!]` No public dataset for `traffic-police motorcycle` → activate the two-stage fallback (A3-B)
- [ ] `[!]` 85% occlusion target missed on 8 CPU → move to ByteTrack + tune `max_age`
- [ ] `[!]` FPS below target → int8 ONNX + smaller `imgsz` + thread tuning
- [ ] `[!]` Training on frames from the test clip → invalid evaluation; document or avoid
