import os
from openimages.download import download_dataset

OUTPUT_DIR = r"D:/Computer_Vision_Course-main/computer_vision/data/datasets"

print("جاري تنزيل صور الفان (Van)...")

download_dataset(
    dest_dir=OUTPUT_DIR,
    class_labels=["Van"],
    limit=500
)

print("تم تنزيل الصور والملفات المرافقة بنجاح في مجلد المشروع!")