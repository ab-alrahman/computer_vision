from roboflow import Roboflow

# تنزيل مجموعة بيانات جاهزة وموسومة لسيارات الفان
rf = Roboflow(api_key="zeyXbmWTVrmC4Ulz5H3F") # أو استخدم API Key الخاص بك من حسابك
project = rf.workspace("roboflow-100-models").project("van-detection")
dataset = project.version(1).download("yolov8")

print("تم تنزيل البيانات في المجلد:", dataset.location)