# عقد الـ API والنظام المتكامل — Smart Toll Road (وثيقة نقاش)

> هذه وثيقة **للنقاش قبل التنفيذ**، وليست كودًا.
>  الأطراف المتعاقد: `vision-service (Python)` <-> `api (NestJS)` <-> `postgres` <-> `mobile (React Native)`.
> المرجع: `docs/code_artifact.md` (التوصيف) و `docs/system_design.md` (معمارية الرؤية).

---

## 0. لماذا نتوسّع؟

التوصيف يطلب ثلاثة أشياء لا يقدّمها سكريبت بايثون وحده:
1. **تنبيه فوري للشرطة** → يحتاج قناة توصيل (تطبيق + إشعارات) لا `print()`.
2. **تقرير نهائي** → يحتاج تخزينًا استعلاميًا (PostgreSQL) لا ملف CSV على القرص.
3. **نظام كامل** → يحتاج إدارة جلسات، صلاحيات، سجل تدقيق، ومراقبة.

**القرار المعماري الأهم:** فصل **التقطيع والعدّ (Edge)** عن **التسجيل والتقرير والتنبيه (Server)**.

---

## 1. مخطط المكوّنات

```
┌──────────────────────────────┐
│  vision-service  (Python)    │  ← جهاز الكاميرا / الحافة
│  preprocess → YOLO11n        │
│  → track → speed → rules     │
└──────────────┬───────────────┘
               │ (1) Ingest: HTTP batch   (2) Config: pull
               ▼
┌──────────────────────────────┐   (3) Realtime fan-out
│      api  (NestJS)           │ ──► WebSocket ──► React Native
│  auth · sessions · alerts    │ ──► Push  (FCM/APNs)
│  reports · config · RBAC     │ ──► MJPEG / HLS
└──────────────┬───────────────┘
               │ (4) SQL
               ▼
        ┌──────────────┐        (5) Redis اختياري: طابور + pub/sub + cache
        │  PostgreSQL  │◄────────►
        └──────────────┘

        اختياري: MinIO/S3 (فيديو مُعلَّم + لقطات المخالفات)
```

### 1.1 من يفعل ماذا (مصدر الحقيقة)

| الطرف | مسؤول عن | ملاحظة |
|---|---|---|
| `vision-service` | الرؤية، التتبع، العدّ، السرعة، رصد المخالفات | زمن حقيقي، **لا يكتب في PostgreSQL أبدًا** |
| `api (NestJS)` | الهوية، الجلسات، الإعدادات، التنبيهات، التقارير، التدقيق | **مصدر الحقيقة الدائم** |
| `postgres` | كل ما هو دائم | العدّ النهائي يأتي من `events` المعتمدة |
| `mobile` | الاستقبال، التأكيد (ACK)، عرض التقارير | يعمل offline للقراءة |

> **قاعدة ذهبية:** العدّ يحدث مرة واحدة داخل Python، و PostgreSQL هو **السجل الرسمي**، و NestJS هو **البوابة الوحيدة** للكتابة. لا شيء يكتب في القاعدة خارج الـ API.

---

## 2. اصطلاحات الـ API

| البند | القرار | السبب |
|---|---|---|
| Base URL | `https://{host}/api/v1` | Versioning في المسار |
| الترميز | `application/json; charset=utf-8` | دعم العربية |
| أسماء الحقول | `camelCase` في JSON و `snake_case` في SQL | توافق مع TypeORM/Prisma |
| الأختام الزمنية | ISO-8601 بتوقيت UTC دائمًا | لا لبس |
| المبالغ المالية | `number` بخانتين في JSON و `numeric(8,2)` في SQL | تفادي خطأ الفاصلة العائمة |
| الترقيم | `?page=1&pageSize=50` مع `{ items, page, pageSize, total }` | جداول الأحداث كبيرة |
| الأخطاء | `{ error: { code, message, details?, traceId } }` | `code` ثابت ليتعامل معه التطبيق |
| اللغة | كل النصوص قابلة للترجمة `ar` / `en` | النظام عربي أولًا |
| المصدر الوحيد للحقيقة | **OpenAPI 3.1** + JSON Schema، وتوليد أنواع React Native آليًا | صفر انحراف بين الأطراف الثلاثة |

---

## 3. المصطلحات (Glossary)

| المصطلح | المعنى | القيم |
|---|---|---|
| **Site** | موقع الطريق (قد يكون أكثر من واحد) | — |
| **Side** | جانب الطريق / موقع|SWE |
| **Direction** | اتجاه العبور | `OUTBOUND` (ذهاب) / `INBOUND` (إياب) |
| **Class** | نوع المركبة | `CAR, VAN, BUS, TRUCK, MOTORCYCLE, TRAFFIC_POLICE_MOTORCYCLE` |
| **Session** | تشغيل واحد للخط الأنابيب | `RUNNING / STOPPED / CRASHED` |
| **Track** | هوية مركبة عبر الزمن داخل Session | `externalTrackId` (عدد صحيح من Python) |
| **Event** | حدث موحّد | `PASSAGE / SPEED_VIOLATION / MOTORCYCLE_VIOLATION` |
| **Alert** | إشعار مُرسل لجهة معينة | `PENDING / SENT / DELIVERED / ACKED / FAILED` |
| **ApproachFrom** | جهة قدوم المخالف (تظهر في نص الرسالة) | `LEFT / RIGHT / NORTH / SOUTH` |

> **نقاش:** `Side` و `Direction` كيانان منفصلان؟ اقتراحي: `Direction` منطقي (ذهاب/إياب)، و `Side` فيزيائي (أين stationedت الشرطة)، و `ApproachFrom` يُشتق من متجه الحركة. لا تخلط الثلاثة.

---

## 4. المصادقة (Auth)

| النوع | الآلية | المستخدم |
|---|---|---|
| **آلة (Python)** | ترويسة `X-Api-Key` (مفتاح لكل جهاز) | vision-service |
| **مستخدم** | `Authorization: Bearer <JWT>` — وصول 15 دقيقة + تجديد 30 يوم | موظف أو شرطي |
| **WebSocket** | نفس الـ JWT أثناء المصافحة | |

الأدوار: `ADMIN` (كل شيء) · `OPERATOR` (يشغّل الجلسات ويقرأ التقارير) · `POLICE` (تنبيهات جهته فقط + ملخص) · `VIEWER` (قراءة فقط).

---

## 5. العقود الجوهرية

### 5.1 إنشاء Session
```http
POST /api/v1/sessions
{
  "siteId": "uuid",
  "sideId": "uuid|null",
  "source": { "type": "FILE",  "ref": "toll_0400_0900.mp4" },
  "mode": "REALTIME",
  "overrides": { "speedLimitKph": 80, "confThreshold": 0.35 }
}
```
الرد `201` يعيد معرّف الجلسة و **مكان الكتابة** وقواعد العمل المطبَّقة، فيبدأ الـ vision-service فورًا.

### 5.2 الـ Ingest (Python ← NestJS) — العقد الأهم
إرسال على دفعات كل ثانية (أو عند امتلاء الدفعة).

```http
POST /api/v1/ingest/sessions/{sessionId}/batch
X-Api-Key: <device key>
```
```json
{
  "deviceId": "uuid",
  "sentAt": "2026-09-26T08:15:30.000Z",
  "stats": { "fps": 22.4, "frameIndex": 45000, "latencyMs": 45, "activeTracks": 7 },
  "events": [
    {
      "eventId": "uuid",
      "type": "PASSAGE",
      "occurredAt": "2026-09-26T08:15:29.800Z",
      "frameIndex": 44987,
      "track": { "externalId": 42, "class": "CAR", "confidence": 0.93 },
      "direction": "OUTBOUND",
      "side": "NORTH",
      "speedKph": 62.1,
      "amount": 1.0,
      "violation": null,
      "meta": { "entryTs": "...", "exitTs": "...", "configVersion": 12 }
    },
    {
      "eventId": "uuid",
      "type": "MOTORCYCLE_VIOLATION",
      "occurredAt": "2026-09-26T08:15:29.900Z",
      "track": { "externalId": 51, "class": "MOTORCYCLE", "confidence": 0.88 },
      "direction": "INBOUND",
      "side": "SOUTH",
      "approachFrom": "RIGHT",
      "speedKph": 45.0,
      "amount": 0,
      "violation": { "code": "MOTORCYCLE_FORBIDDEN", "severity": "HIGH" },
      "meta": { "snapshotKey": "minio://violations/2026-09-26/xxx.jpg" }
    }
  ]
}
```
الرد:
```json
{ "accepted": 2, "duplicates": 0, "alertsCreated": 1 }
```

**قواعد الـ Ingest:**
- `eventId` هو **مفتاح عدم التكرار**: إعادة إرسال الدفعة نفسها لا تُضاعف العدّ.
- **مَن يولّد التنبيه؟** اقتراحي: **الـ API** (مركزي)، فيرسل Python فقط الأحداث ويُخبره `alertsCreated`.
- عند انقطاع الشبكة: طابور محلي في Python + إعادة إرسال لاحقًا (سلامة بفضل `eventId`).

### 5.3 Heartbeat
```http
POST /api/v1/ingest/sessions/{id}/heartbeat
{ "deviceId":"uuid", "fps":22.4, "latencyMs":45, "status":"RUNNING", "configVersion":12 }
```
الرد: `{ "ok": true, "configVersion": 13 }` — إذا اختلف الرقم، يسحب Python الحزمة الجديدة.

### 5.4 مظروف الحدث الموحّد (يُستخدم في WebSocket أيضًا)
```json
{
  "type": "event.detected",
  "sessionId": "uuid",
  "seq": 10293,
  "ts": "2026-09-26T08:15:29.800Z",
  "data": { }
}
```

### 5.5 التنبيهات (Alerts)
```http
POST /api/v1/alerts                 # يدوي أو للاختبار
GET  /api/v1/alerts?sideId=&sessionId=&status=&page=
GET  /api/v1/alerts/{alertId}
POST /api/v1/alerts/{alertId}/ack   { "note": "تم التحرك" }
```
شكل التنبيه الذي يصل للشرطي:
```json
{
  "id": "uuid",
  "severity": "HIGH",
  "targetSide": "NORTH",
  "title": "مخالفة دراجة نارية",
  "body": "انتبه مرور مخالف قادم إليك - يمين",
  "violationCode": "MOTORCYCLE_FORBIDDEN",
  "approachFrom": "RIGHT",
  "sessionId": "uuid",
  "occurredAt": "2026-09-26T08:15:29.800Z",
  "status": "PENDING",
  "snapshotUrl": "https://cdn.example.com/violations/xxx.jpg",
  "etaSeconds": 12
}
```
> **مقترح إضافي:** `etaSeconds` = كم ثانية حتى يصل المخالف، يُحسب من السرعة والمسافة ويُضبط لكل موقع. ميزة قوية للشرطة.

### 5.6 التقارير
```http
GET /api/v1/sessions/{id}/report
GET /api/v1/sessions/{id}/report?format=csv|xlsx|pdf
GET /api/v1/reports/daily?siteId=&date=2026-09-26
```
```json
{
  "sessionId": "uuid",
  "site": { "id": "uuid", "name": "طريق الحقة" },
  "window": { "from": "...", "to": "..." },
  "matrix": {
    "OUTBOUND": { "CAR": 42, "VAN": 7, "BUS": 3, "TRUCK": 5, "MOTORCYCLE": 1, "TRAFFIC_POLICE_MOTORCYCLE": 0 },
    "INBOUND":  { "CAR": 38, "VAN": 9, "BUS": 2, "TRUCK": 6, "MOTORCYCLE": 0, "TRAFFIC_POLICE_MOTORCYCLE": 1 }
  },
  "revenue": { "OUTBOUND": 61.5, "INBOUND": 58.0, "total": 119.5, "currency": "USD" },
  "violations": {
    "MOTORCYCLE_VIOLATION": 1,
    "SPEED_VIOLATION": 4,
    "speedingDetails": [
      { "trackExternalId": 88, "class": "TRUCK", "speedKph": 97, "limitKph": 80, "at": "..." }
    ]
  },
  "generatedAt": "..."
}
```

### 5.7 الإعدادات (تُدفع إلى Python)
```http
GET /api/v1/config/bundle?sessionId=
PUT /api/v1/config/tolls         { "CAR":1.0, "VAN":1.5, "BUS":2.0, "TRUCK":2.5, "MOTORCYCLE":0, "TRAFFIC_POLICE_MOTORCYCLE":0 }
PUT /api/v1/config/speed-limits { "default": 80, "perSide": { "NORTH": 60, "SOUTH": 80 } }
PUT /api/v1/config/lines         { "OUTBOUND": [[x,y],[x,y]], "INBOUND": [[x,y],[x,y]], "deadbandPx": 12 }
GET /api/v1/config/classes
```
كل تعديل يرفع `configVersion`، فيسحبه Python عند `heartbeat`.

---

## 6. جدول الـ REST Endpoints

| Method | Path | الصلاحية | الوصف |
|---|---|---|---|
| POST | `/auth/login` · `/auth/refresh` · `/auth/logout` | عام / JWT | المصادقة |
| GET | `/auth/me` | JWT | المستخدم الحالي |
| GET POST | `/sites` · `/sites/{id}/sides` | JWT+ | إدارة المواقع والجهات |
| GET POST | `/devices` · `/devices/{id}/apikey` | ADMIN | الأجهزة ومفاتيحها |
| POST | `/sessions` | OPERATOR+ | بدء جلسة |
| GET | `/sessions?siteId=&status=&page=` | JWT | قائمة الجلسات |
| GET | `/sessions/{id}` | JWT | التفاصيل والعدادات الحية |
| POST | `/sessions/{id}/stop` | OPERATOR+ | إنهاء وتوليد التقرير |
| GET | `/sessions/{id}/events?type=&class=&direction=&page=` | JWT | الأحداث |
| GET | `/sessions/{id}/tracks` | JWT | المسارات (فحص التداخل) |
| GET | `/sessions/{id}/violations` | JWT | المخالفات |
| GET | `/sessions/{id}/report?format=` | JWT | التقرير النهائي |
| GET | `/sessions/{id}/stream` | JWT | البث الحي |
| POST | `/ingest/sessions/{id}/batch` | `X-Api-Key` | ingest دفعة أحداث |
| POST | `/ingest/sessions/{id}/heartbeat` | `X-Api-Key` | الحالة + جلب الإعدادات |
| GET | `/alerts?sideId=&status=` | JWT | التنبيهات |
| POST | `/alerts/{id}/ack` | POLICE | تأكيد الاستلام |
| GET PUT | `/config/*` | JWT | الرسوم والسرعة والخطوط والألوان |
| GET | `/healthz` · `/metrics` | عام | الصحة ومقاييس Prometheus |
| GET | `/audit-log` | ADMIN | سجل التدقيق |

---

## 7. الطبقة اللحظية (Realtime)

### 7.1 قنوات WebSocket
| القناة | المشترك | الأحداث |
|---|---|---|
| `ws /ws/sessions/{id}` | لوحة المتابعة | `counter.updated` · `event.detected` · `session.stats` · `session.state` |
| `ws /ws/sides/{sideId}/alerts` | **تطبيق الشرطة** | `alert.created` · `alert.updated` |
| `ws /ws/sessions/{id}/boxes` | الهاتف (رسم المربعات) | `box.frame` |

كل رسالة تحمل `seq` تصاعديًا، فإذا انقطع الاتصال يعيد العميل `?sinceSeq=` فيستأنف.

### 7.2 إشعارات الهاتف في الخلفية
`alert.created` ← NestJS يرسل **FCM / APNs** ← التطبيق يظهر تنبيهًا حتى لو كان مغلقًا.

### 7.3 البث المرئي
| الخيار | المزايا | العيوب |
|---|---|---|
| **MJPEG** (multipart) — *مقترح للبداية* | بسيط، عبر HTTP، يعمل مباشرة على React Native | استهلاك نطاق عالٍ، تأخير 1-2 ثانية |
| HLS (`.m3u8`) | قياسي، أصلي في iOS و Android | تأخير 5-15 ثانية (ليس لحظيًا) |
| WebRTC | الأفضل في الإنتاج | إعداد معقّد وبروتوكول كامل |

> **نقاش:** هل يحتاج التطبيق **بثًا حيًا بالمربعات** فعلًا، أم تكفي **لقطة عند التنبيه + عدّادات حية**؟ الخيار الثاني أنظف وأخف بكثير.

### 7.4 رسم المربعات على الهاتف
لا نرسل فيديو معالَجًا، بل **إحداثيات** فقط عبر WebSocket:
```json
{ "type":"box.frame", "frameIndex":44987,
  "boxes":[ { "id":42, "class":"CAR", "color":"#3B82F6", "rect":[0.31,0.42,0.22,0.18], "violation":false } ],
  "counters": { "OUTBOUND": { "CAR": 42 } } }
```
والتطبيق يرسمها بمكتبة `react-native-svg`. رخيص وفوري، ولا يحتاج معالجة على السيرفر.

---

## 8. تطبيق الشرطة (React Native)

| الشاشة | الـ API | ملاحظات |
|---|---|---|
| **تسجيل الدخول** | `POST /auth/login` | يربط الجهاز بموقع واحد |
| **الرئيسية** | `GET /alerts?sideId=me` + WS | التنبيهات غير المقروءة في الأعلى |
| **العرض الحي** | `GET /sessions/{id}/stream` + WS | مربعات + عدّادات |
| **قائمة التنبيهات** | `GET /alerts?status=` | تصفية: pendante / مؤكَّد |
| **تفاصيل التنبيه** | `GET /alerts/{id}` + `POST /alerts/{id}/ack` | زر تأكيد كبير + زر اتصال |
| **التقارير** | `GET /sessions/{id}/report` + `/reports/daily` | جدول المصفوفة والدخل |
| **الإعدادات** | `GET /config/*` | اللغة، الإشعارات، حد السرعة |

مخزن محلي: `react-query` + `AsyncStorage` للقراءة دون اتصال، و`Notifee` + `Firebase Messaging` للتنبيهات.

---

## 9. مخطط PostgreSQL (مسودّة)

```sql
-- المواقع والجهات
sites(id UUID PRIMARY KEY, name TEXT, road_name TEXT,
      currency TEXT DEFAULT 'USD', created_at TIMESTAMPTZ);
sides(id UUID PRIMARY KEY, site_id UUID REFERENCES sites,
      code TEXT, label TEXT, geo POINT, eta_meters INT,
      UNIQUE(site_id, code));

-- الأجهزة
devices(id UUID PRIMARY KEY, site_id UUID REFERENCES sites,
        name TEXT, kind TEXT, api_key_hash TEXT UNIQUE,
        status TEXT, last_seen_at TIMESTAMPTZ, meta JSONB);

-- المستخدمون
users(id UUID PRIMARY KEY, email CITEXT UNIQUE, password_hash TEXT,
      full_name TEXT, role TEXT, side_id UUID REFERENCES sides,
      is_active BOOLEAN, created_at TIMESTAMPTZ);
refresh_tokens(id UUID PRIMARY KEY, user_id UUID REFERENCES users,
               token_hash TEXT, expires_at TIMESTAMPTZ);
push_tokens(id UUID PRIMARY KEY, user_id UUID REFERENCES users,
            platform TEXT, token TEXT UNIQUE, last_seen_at TIMESTAMPTZ);

-- الجلسات
sessions(id UUID PRIMARY KEY, site_id UUID REFERENCES sites,
         device_id UUID, operator_id UUID,
         source_type TEXT, source_ref TEXT, mode TEXT, status TEXT,
         started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ,
         config_snapshot JSONB, stats JSONB, report JSONB);

-- المسارات (لفحص التداخل)
tracks(id BIGSERIAL PRIMARY KEY, session_id UUID REFERENCES sessions,
       external_track_id INT, class_code TEXT, confidence NUMERIC(4,3),
       direction TEXT, side_code TEXT,
       entered_at TIMESTAMPTZ, exited_at TIMESTAMPTZ,
       speed_avg_kph NUMERIC(6,2), speed_max_kph NUMERIC(6,2),
       toll_amount NUMERIC(8,2) DEFAULT 0, is_violation BOOLEAN,
       UNIQUE(session_id, external_track_id));

-- الأحداث (مصدر الحقيقة للعدّ)
events(id UUID PRIMARY KEY,               -- نفسه eventId الخاص بـ Python
       session_id UUID REFERENCES sessions, track_id BIGINT REFERENCES tracks,
       type TEXT, occurred_at TIMESTAMPTZ, frame_index INT,
       class_code TEXT, direction TEXT, side_code TEXT, approach_from TEXT,
       speed_kph NUMERIC(6,2), amount NUMERIC(8,2),
       payload JSONB, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX ON events(session_id, type, occurred_at);
CREATE INDEX ON events(session_id, class_code, direction);

-- التنبيهات
alerts(id UUID PRIMARY KEY, event_id UUID UNIQUE REFERENCES events,
       session_id UUID, target_side_id UUID REFERENCES sides,
       severity TEXT, approach_from TEXT, title TEXT, body TEXT,
       status TEXT DEFAULT 'PENDING', snapshot_key TEXT,
       created_at TIMESTAMPTZ, sent_at TIMESTAMPTZ, delivered_at TIMESTAMPTZ,
       acked_at TIMESTAMPTZ, acked_by UUID, ack_note TEXT);

-- سجل التدقيق
audit_log(id BIGSERIAL PRIMARY KEY, actor_id UUID, action TEXT,
          entity TEXT, entity_id TEXT, before JSONB, after JSONB,
          at TIMESTAMPTZ DEFAULT now());
```

**العلاقة الحاسمة:** `events.id` (= `eventId` من Python) هو مفتاح عدم التكرار، و `alerts.event_id` فريد — أي تنبيه واحد لكل مخالفة مهما تكرّرت الدفعة.

---

## 10. نموذج الأخطاء

```json
{ "error": {
    "code": "SESSION_NOT_RUNNING",
    "message": "الجلسة غير قيد التشغيل",
    "details": { "sessionId": "..." },
    "traceId": "8f2c..." } }
```

| code | HTTP | متى |
|---|---|---|
| `VALIDATION_ERROR` | 400 | جسم الطلب غير مطابق |
| `UNAUTHENTICATED` | 401 | توكن منتهي أو غائب |
| `FORBIDDEN` | 403 | صلاحية غير كافية |
| `NOT_FOUND` | 404 | غير موجود |
| `CONFLICT` | 409 | مثلًا تشغيل جلسة نشطة |
| `RATE_LIMITED` | 429 | إرسال أسرع من المسموح |
| `INTERNAL` | 500 | خطأ داخلي |

---

## 11. الموثوقية في الميدان

| القلق | القرار |
|---|---|
| انقطاع الشبكة بين Python و API | طابور محلي + إعادة إرسال؛ `eventId` يمنع التكرار |
| انقطاع شبكة الشرطي | التطبيق يخزّن التنبيهات محليًا، و WebSocket يستأنف بـ `sinceSeq` |
| تكرار الإرسال | كل نقطة إدخال **idempotent** بمفتاح `eventId` |
| ضغط الطلبات | `429` مع `Retry-After`؛ Python يخفّض الإرسال ولا يُهمل الأحداث |
| المراقبة | `/metrics`: الإطارات، التأخير، طول الطابور، معدل التنبيهات، أخطاء الإدخال |

---

## 12. أسئلة للنقاش

**أ) الاتصال بين Python و NestJS**
1. نكتفي بـ `POST /ingest/.../batch` كل ثانية، أم نُدخل **Redis** كطابور بينهما؟ (اقتراحي: ابدأ HTTP، وأضف Redis إذا تأخّر الإدخال)
2. مَن يولّد التنبيه: الـ API (مركزي) أم Python؟

**ب) الطبقة اللحظية**
3. الهاتف يحتاج **بثًا حيًا بالمربعات**، أم **لقطة + عدّادات** تكفي؟ (هذا يحدّد MJPEG أو لقطة فقط)
4. هل نضيف `etaSeconds` (متى يصل المخالف) إلى التنبيه؟

**ج) الهوية والصلاحيات**
5. لكل جهة حساب شرطة مستقل، أم حساب واحد بدور `POLICE` مع تبديل الجهة من التطبيق؟

**د) العدّ**
6. هل نسمح بتصحيح يدوي للأعداد من لوحة المتابعة؟ (اقتراحي: نعم، مع `audit_log`)

**هـ) التطبيق**
7. التطبيق لـ **الشرطة فقط**، أم للشرطة والمشرف معًا؟ (يحدّد عدد الأدوار والشاشات)

**و) البنية**
8. `docker-compose` للتطوير و Kubernetes للتشغيل؟ و PostgreSQL مُدار أم محلي؟

**ز) التخزين**
9. نحفظ **الفيديو المُعلَّم** ولقطات المخالفات في MinIO/S3، أم نتجاهل ذلك؟

**ح) اللغة**
10. رسائل التنبيه بالعربية فقط أم ثنائية اللغة (ar/en)؟

**ط) مصدر الفيديو**
11. مصادر النظام: رفع ملف، أم بث RTSP حي، أم كلاهما؟

---

## 13. ملخص القرارات المقترحة

1. **افصل المسؤوليات:** Python للعد اللحظي، NestJS للتسجيل والتنبيه، PostgreSQL للحقيقة الدائمة، React Native للاستقبال.
2. **عقد واحد حاكم:** `eventId` لمنع التكرار + مظروف حدث موحّد + OpenAPI 3.1 لتوليد الأنواع.
3. **الحد الأدنى القابل للتسليم:** Session + Ingest + Report + Alert + WebSocket + Push (بدون بث مرئي، لقطة فقط).
4. **نقطة الانطلاق:** نكتب OpenAPI لثلاثة عقود (Session, Ingest-Batch, Alert-Ack) + مخطط SQL، ونصادق عليها قبل أي كود.
