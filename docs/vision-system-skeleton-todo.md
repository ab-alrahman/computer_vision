# Vision System Skeleton TODO

> الهدف من هذا الملف هو تنظيم شغل بناء الهيكلة الأساسية لنظام الرؤية قبل الدخول في التدريب النهائي أو بناء API/Dashboard كامل.
> النسخة الأولى تكون CLI محلية: تدخل فيديو، تطلع فيديو مرسوم عليه النتائج وتقرير JSON/CSV.

## Phase 0 - تثبيت النطاق

- [x] النسخة الأولى تعمل من CLI فقط، بدون Dashboard وبدون API.
- [x] الإدخال يكون فيديو محلي.
- [x] الإخراج يكون annotated video + report JSON.
- [x] الموديل الافتراضي هو `models/yolo11n.pt`.
- [x] مسار الموديل يكون قابل للتبديل لاحقا إلى `models/yolo11n-toll.pt`.
- [x] لا ندخل في Fine-tuning داخل هذا المسار، فقط نجهز النظام ليستقبل الموديل المدرب لاحقا.

## Phase 1 - هيكل المجلدات

- [x] إنشاء `src/`.
- [x] إنشاء `src/core/`.
- [x] إنشاء `src/pipeline/`.
- [x] إنشاء `src/services/`.
- [x] إنشاء `tests/`.
- [x] إنشاء `configs/default.yaml`.
- [x] التأكد أن التشغيل الأساسي يتم عبر `python -m src.main --config configs/default.yaml`.

## Phase 2 - تعريف أنواع البيانات

- [x] تعريف `VehicleClass`.
- [x] تعريف `Direction`.
- [x] تعريف `Detection`.
- [x] تعريف `Track`.
- [x] تعريف `PassageEvent`.
- [x] تعريف `ViolationEvent`.
- [x] تعريف `FrameResult`.
- [x] حفظ التعاريف في `src/core/types.py`.

## Phase 3 - Config

- [x] قراءة الإعدادات من YAML.
- [x] إعداد `model_path`.
- [x] إعداد `input_video`.
- [x] إعداد `output_video`.
- [x] إعداد `report_path`.
- [x] إعداد `confidence_threshold`.
- [x] إعداد class colors.
- [x] إعداد counting lines.
- [x] إعداد toll prices.
- [x] إعداد speed limit كـ placeholder.
- [x] إضافة test لتحميل config.

## Phase 4 - Video Source

- [x] `src/pipeline/source.py` يفتح الفيديو.
- [x] قراءة الفيديو frame by frame.
- [x] إرجاع `frame_index`.
- [x] إرجاع timestamp.
- [x] إرجاع صورة frame.
- [x] إضافة smoke test للتأكد أن الفيديو يفتح ويقرأ أول frame.

## Phase 5 - Detector

- [x] `src/pipeline/detector.py` يحمل YOLO11n.
- [x] تنفيذ inference على frame.
- [x] تحويل نتائج YOLO إلى `Detection`.
- [x] فلترة فئات المركبات فقط.
- [x] دعم `model_path` من config.
- [x] دعم confidence threshold من config.
- [x] إبقاء الكود جاهزا لاستبدال `yolo11n.pt` لاحقا بـ `yolo11n-toll.pt`.

## Phase 6 - Tracker MVP

- [x] بناء tracker بسيط كبداية: Centroid أو IoU.
- [x] إعطاء `track_id` ثابت قدر الإمكان.
- [x] إدارة حالة track: active / lost.
- [x] حفظ آخر مركز لكل track.
- [x] حفظ `counted = false/true`.
- [x] حذف tracks القديمة بعد عدد frames محدد.

## Phase 7 - Geometry & Counting

- [x] تعريف counting line واحد كبداية.
- [x] كشف عبور track للخط.
- [x] تحديد اتجاه تقريبي: `INBOUND` أو `OUTBOUND`.
- [x] منع العد المكرر لنفس track.
- [ ] إضافة deadband بسيط حول الخط لاحقا إذا ظهرت مشكلة توقف فوق الخط.
- [x] إضافة test لعبور الخط.
- [x] إضافة test لمنع العد المكرر.

## Phase 8 - Rules

- [x] حساب رسوم العبور حسب نوع المركبة.
- [x] تسجيل `PASSAGE` event عند العبور.
- [x] تسجيل `MOTORCYCLE_VIOLATION` للدراجات العادية.
- [x] تجاهل المخالفة لـ `traffic-police motorcycle`.
- [x] تجهيز placeholder لـ `SPEED_VIOLATION`.
- [x] إضافة test لحساب الرسوم.

## Phase 9 - Annotator

- [ ] رسم bounding boxes.
- [ ] رسم `track_id`.
- [ ] رسم class name.
- [ ] رسم confidence.
- [ ] رسم counting line.
- [ ] رسم counters على الفيديو.
- [ ] التأكد أن اللون الأحمر محجوز فقط للمخالفات.

## Phase 10 - Report

- [ ] تجميع counts حسب class + direction.
- [ ] حساب total revenue.
- [ ] حفظ قائمة passages.
- [ ] حفظ قائمة violations.
- [ ] إخراج `report.json`.
- [ ] إخراج `report.csv` لاحقا.

## Phase 11 - Main CLI

- [ ] إنشاء `src/main.py`.
- [ ] إضافة CLI argument باسم `--config`.
- [ ] تشغيل pipeline كامل:
  `source -> detector -> tracker -> geometry -> rules -> annotator -> report`.
- [ ] طباعة ملخص في نهاية التشغيل: عدد المركبات، المخالفات، الدخل، مسارات الملفات الناتجة.

## Phase 12 - Tests

- [ ] test تحميل config.
- [ ] test حساب الرسوم.
- [ ] test عبور الخط.
- [ ] test منع العد المكرر.
- [ ] test rule الخاصة بـ motorcycle violation.

## Suggested Execution Order

1. Phase 1 - هيكل المجلدات.
2. Phase 2 - أنواع البيانات.
3. Phase 3 - Config.
4. Phase 4 - Video Source.
5. Phase 5 - Detector.
6. Phase 6 + Phase 7 - Tracking and counting.
7. Phase 8 + Phase 10 - Rules and report.
8. Phase 9 + Phase 11 - Annotated video and CLI integration.
9. Phase 12 - Tests مع كل مرحلة، وليس في النهاية فقط.
