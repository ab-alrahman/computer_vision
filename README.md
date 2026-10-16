# نظام المرور الذكي

مشروع رؤية حاسوبية لتحليل فيديو طريق، واكتشاف المركبات وتصنيفها وتتبعها وعدّها حسب اتجاه الحركة، مع حساب الرسوم وتسجيل مخالفات السرعة والدراجات النارية.

## المتطلبات

- Python 3.10 أو أحدث.
- يفضّل وجود بطاقة NVIDIA للتدريب السريع، لكن التشغيل ممكن على CPU.
- النموذج الجاهز موجود داخل `models/best.pt`.
- الفيديو يوضع داخل `data/raw/video/`.

## التثبيت

افتح PowerShell داخل مجلد المشروع ونفّذ:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

إذا كان لديك Python مثبتاً باسم `py` استخدم `py` بدلاً من `python`.

## التشغيل السريع

للتأكد من أن المشروع يعمل على أول 15 إطاراً فقط:

```powershell
python -m src.main --config configs/default.yaml --max-frames 15
```

لتشغيل الفيديو كاملاً:

```powershell
python -m src.main --config configs/default.yaml --all-frames
```

## تفعيل حساب السرعة

قبل حساب السرعة يجب معايرة الطريق مرة واحدة باختيار أربع نقاط تمثل سطح الطريق:

```powershell
python scripts/calibrate_geometry.py --frame-index 400 --out configs/calibration.json
```

بعد حفظ `configs/calibration.json` شغّل الفيديو كالمعتاد. إذا لم يوجد ملف المعايرة، سيعمل النظام لكن سيعطّل حساب السرعة.

ينتج المشروع:

- فيديو مشروح داخل `runs/vision/output.mp4`.
- تقرير JSON داخل `runs/vision/report.json`.

يتم تحديد اسم الفيديو والنموذج والإعدادات من الملف `configs/default.yaml`. إذا كان اسم الفيديو مختلفاً، عدّل قيمة `video.input` في ذلك الملف.

## التدريب (اختياري)

لا حاجة لإعادة التدريب إذا كان الهدف فحص المشروع فقط؛ استخدم `models/best.pt`. لإعادة التدريب:

```powershell
python scripts/train.py --config configs/train.yaml --smoke --no-export
```

هذا اختبار قصير. أما التدريب الكامل للفئات الست:

```powershell
python scripts/train.py --config configs/train.yaml --eval-test
```

يتم حفظ نتائج التدريب داخل `runs/`.

## بنية المشروع

```text
src/          كود الكشف والتتبع والعد والتقرير
scripts/      التدريب وفحص البيانات والمعايرة
configs/      إعدادات التشغيل والتدريب
data/         ملفات تعريف البيانات والفيديوهات
models/       نماذج YOLO
runs/         النتائج والفيديو والتقارير
docs/         التقرير التفصيلي للمشروع
```

للتفاصيل الكاملة راجع [التقرير التفصيلي](docs/project_report.md).
