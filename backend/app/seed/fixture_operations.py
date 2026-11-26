"""Demo data of the operations modules: AI functions per model, tests, maintenance, development opportunities.
All fictional; dates are day offsets from the seeding day."""
from __future__ import annotations

# model code -> AI technologies it supports
MODEL_AI = {
    "M001": ("COMPUTER_VISION", "OBJECT_DETECTION", "OBJECT_RECOGNITION", "OBJECT_TRACKING", "AUTONOMOUS_NAVIGATION",
             "OBSTACLE_AVOIDANCE"),
    "M002": ("COMPUTER_VISION", "OBJECT_DETECTION", "OBJECT_TRACKING", "AUTONOMOUS_NAVIGATION", "OBSTACLE_AVOIDANCE",
             "BEHAVIOUR_DETECTION"),
    "M003": ("COMPUTER_VISION", "OBJECT_DETECTION", "OBJECT_RECOGNITION", "OBJECT_TRACKING", "AUTONOMOUS_NAVIGATION",
             "PATH_PLANNING", "OBSTACLE_AVOIDANCE", "SENSOR_FUSION", "ANOMALY_DETECTION"),
    "M004": ("COMPUTER_VISION", "OBJECT_DETECTION", "OBJECT_TRACKING"),
    "M005": ("COMPUTER_VISION", "OBJECT_DETECTION", "AUTONOMOUS_NAVIGATION", "PATH_PLANNING"),
    "M006": ("COMPUTER_VISION", "OBJECT_DETECTION", "AUTONOMOUS_NAVIGATION", "OBSTACLE_AVOIDANCE", "PATH_PLANNING"),
    "M007": ("AUTONOMOUS_NAVIGATION",),
    "M008": (),
    "M009": ("OBJECT_DETECTION", "AUTONOMOUS_NAVIGATION", "OBSTACLE_AVOIDANCE"),
    "M010": ("COMPUTER_VISION", "OBJECT_DETECTION", "OBJECT_TRACKING", "AUTONOMOUS_NAVIGATION", "OBSTACLE_AVOIDANCE",
             "SENSOR_FUSION"),
    "M011": ("COMPUTER_VISION",),
    "M012": ("AUTONOMOUS_NAVIGATION", "PATH_PLANNING", "OBSTACLE_AVOIDANCE", "SENSOR_FUSION", "ANOMALY_DETECTION",
             "MISSION_PLANNING", "OBJECT_DETECTION"),
}

# code, English, Arabic, model, project, department, site, type, date offset, status, score, result EN, result AR
TESTS = (
    ("TST-001", "Endurance flight 14 h", "طيران التحمل 14 ساعة", "M001", None, "G2", "TER", "INTERNAL", -240, "PASSED", 92,
     "Met endurance target.", "حقق هدف التحمل."),
    ("TST-002", "SAR pod integration", "دمج حاضنة الرادار", "M001", "PRJ-004", "G2", "TER", "INTERNAL", -150, "CONDITIONAL",
     74, "Image latency above limit.", "زمن تأخر الصورة أعلى من الحد."),
    ("TST-003", "Cross-border link trial", "تجربة الربط عبر الحدود", "M001", "PRJ-004", "G2", None, "EXTERNAL", 30, "PLANNED",
     None, None, None),
    ("TST-004", "Night endurance series", "سلسلة طلعات التحمل الليلي", "M004", "PRJ-008", "G4", "TER", "INTERNAL", -10,
     "IN_PROGRESS", None, None, None),
    ("TST-005", "Detection accuracy test", "اختبار دقة الاكتشاف", "M002", "PRJ-014", "G3", "ECS", "INTERNAL", -70, "PASSED",
     88, "Detection accuracy 94%.", "دقة الاكتشاف 94%."),
    ("TST-006", "Sea trial, sea state 4", "تجربة بحرية حالة بحر 4", "M009", "PRJ-007", "G2", "ECS", "INTERNAL", -20,
     "CANCELLED", None, "Cancelled: weather window lost.", "أُلغيت لفقدان نافذة الطقس."),
    ("TST-007", "Coastal patrol evaluation", "تقييم الدوريات الساحلية", "M009", "PRJ-007", "G2", "ECS", "INTERNAL", -60,
     "CONDITIONAL", 68, "Endurance below target at full load.", "التحمل أقل من الهدف بكامل الحمولة."),
    ("TST-008", "Autonomy navigation 3.2", "اختبار الملاحة الذاتية 3.2", "M006", "PRJ-005", "G1", "TER", "INTERNAL", 25,
     "PLANNED", None, None, None),
    ("TST-009", "Swarm simulation, 6 aircraft", "محاكاة سرب من 6 طائرات", "M003", "PRJ-011", "G1", "CTC", "INTERNAL", -45,
     "FAILED", 42, "Deconfliction failures above six aircraft.", "إخفاق فض التعارض لأكثر من ست طائرات."),
    ("TST-010", "Pressure housing qualification", "تأهيل غلاف الضغط", "M012", "PRJ-012", "G1", "TER", "EXTERNAL", -90,
     "FAILED", 35, "Seal leak at 1,200 m.", "تسرب في مانع التسرب عند 1200 م."),
    ("TST-011", "Predictive maintenance model validation", "التحقق من نموذج الصيانة التنبؤية", "M001", "PRJ-013", "G1",
     "CTC", "INTERNAL", -15, "PASSED", 81, "Fault prediction precision 0.83.", "دقة التنبؤ بالأعطال 0.83."),
    ("TST-012", "EOD manipulator test", "اختبار الذراع الآلية للمتفجرات", "M008", None, "G3", "ECS", "INTERNAL", -120,
     "PASSED", 90, None, None),
    ("TST-013", "Underwater inspection trial", "تجربة الفحص تحت الماء", "M011", None, "G3", "ECS", "INTERNAL", -200,
     "PASSED", 86, None, None),
    ("TST-014", "Ranger-6 desert mobility", "حركية رينجر-6 الصحراوية", "M006", None, "G2", "WSB", "INTERNAL", -300,
     "PASSED", 89, None, None),
    ("TST-015", "Sentinel VTOL acceptance", "قبول ستنيل VTOL", "M003", None, "G1", "TER", "EXTERNAL", -330, "PASSED", 93,
     None, None),
    ("TST-016", "Low-light tracking", "التتبع في الإضاءة المنخفضة", "M004", None, "G2", "NOB", "INTERNAL", -95,
     "CONDITIONAL", 71, "Tracking loss after dusk.", "فقدان التتبع بعد الغسق."),
    ("TST-017", "Datalink range trial", "تجربة مدى وصلة البيانات", "M010", None, "G3", "ECS", "INTERNAL", 60, "PLANNED",
     None, None, None),
    ("TST-018", "Battery thermal test", "اختبار حرارة البطارية", "M002", "PRJ-002", "G3", "TER", "INTERNAL", 80, "PLANNED",
     None, None, None),
)

# The section (reference_data.ORG_UNITS) that conducts each test.
TEST_UNITS = {
    "TST-001": "CAP-DEV", "TST-002": "SEC-SYS", "TST-003": "SEC-SYS", "TST-004": "CAP-DEV", "TST-005": "SEC-SYS",
    "TST-006": "CAP-DEV", "TST-007": "SEC-SYS", "TST-008": "CAP-DEV", "TST-009": "CAP-DEV", "TST-010": "CAP-DEV",
    "TST-011": "CAP-DEV", "TST-012": "SEC-SYS", "TST-013": "SEC-SYS", "TST-014": "CAP-DEV", "TST-015": "CAP-DEV",
    "TST-016": "SEC-SYS", "TST-017": "SEC-SYS", "TST-018": "CAP-DEV",
}

# code, asset code, type, English, Arabic, status, start offset, expected end offset, actual end offset, progress,
# cost, parts shortage, parts
MAINTENANCE = (
    ("MNT-001", "UAV-008", "CORRECTIVE", "Engine vibration fault", "عطل اهتزاز المحرك", "IN_PROGRESS", -30, -5, None, 60,
     120_000, 0, None),
    ("MNT-002", "UAV-021", "CORRECTIVE", "Landing gear fault", "عطل في ترس الهبوط", "AWAITING_PARTS", -25, 10, None, 35,
     65_000, 1, "Sensor module, wiring harness"),
    ("MNT-003", "UGV-005", "PREVENTIVE", "500-hour service", "الفحص المجدول لكل 500 ساعة", "IN_PROGRESS", -12, 3, None, 47,
     40_000, 1, "Seal kit"),
    ("MNT-004", "UAV-009", "CORRECTIVE", "Flight controller replacement", "استبدال وحدة التحكم بالطيران", "AWAITING_PARTS",
     -40, -8, None, 20, 210_000, 1, "Flight controller"),
    ("MNT-005", "USV-002", "PREVENTIVE", "Hull inspection", "فحص البدن", "COMPLETED", -90, -80, -78, 100, 30_000, 0, None),
    ("MNT-006", "UUV-002", "CORRECTIVE", "Tether connector repair", "إصلاح موصل الكابل", "IN_PROGRESS", -8, 7, None, 70,
     18_000, 0, None),
    ("MNT-007", "UAV-001", "PREVENTIVE", "100-hour inspection", "فحص كل 100 ساعة", "COMPLETED", -60, -55, -55, 100,
     12_000, 0, None),
    ("MNT-008", "UAV-030", "UPGRADE", "Hydraulic pump replacement", "استبدال مضخة الهيدروليك", "IN_PROGRESS", -20, -2, None,
     24, 95_000, 1, "Hydraulic pump"),
    ("MNT-009", "UGV-002", "CORRECTIVE", "Battery unit degradation", "تدهور وحدة البطارية", "IN_PROGRESS", -15, 12, None,
     30, 55_000, 1, "Battery pack"),
    ("MNT-010", "USV-004", "INSPECTION", "Radar calibration", "معايرة الرادار", "PLANNED", 10, 14, None, 0, 8_000, 0, None),
    ("MNT-011", "UAV-022", "CORRECTIVE", "Camera gimbal fault", "عطل حامل الكاميرا", "COMPLETED", -50, -40, -36, 100,
     22_000, 0, None),
    ("MNT-012", "UGV-010", "PREVENTIVE", "Track replacement", "استبدال الجنزير", "COMPLETED", -120, -110, -104, 100,
     48_000, 0, None),
)

# Why the capability entered maintenance (Maintenance > Capability maintenance): order code -> (English, Arabic).
MAINTENANCE_REASONS = {
    "MNT-001": ("Strong engine vibration reported by the crew after a reconnaissance sortie; the aircraft was grounded.",
                "اهتزاز قوي في المحرك أبلغ عنه الطاقم بعد طلعة استطلاع، وأوقفت الطائرة عن الطيران."),
    "MNT-002": ("Hard landing at the end of a training mission damaged the landing gear.",
                "هبوط قاسٍ في نهاية مهمة تدريبية أدى إلى تضرر ترس الهبوط."),
    "MNT-004": ("Loss of control link twice in one week; the investigation board traced it to the flight controller.",
                "فقدان وصلة التحكم مرتين خلال أسبوع، وأرجعت هيئة التحقيق السبب إلى وحدة التحكم بالطيران."),
    "MNT-009": ("Battery capacity fell below 60 % of rated during the readiness check.",
                "انخفضت سعة البطارية إلى أقل من 60٪ من السعة المقررة أثناء فحص الجاهزية."),
}

# Golden-sample trials: code, model, English, Arabic, days from today, status, notes EN, notes AR
GOLDEN_TRIALS = (
    ("GS-001", "M001", "Golden sample acceptance flight", "طيران قبول العينة الذهبية", -45, "PASSED",
     "Endurance and payload within specification.", "التحمل والحمولة ضمن المواصفات."),
    ("GS-002", "M003", "Golden sample swarm coordination trial", "تجربة تنسيق السرب للعينة الذهبية", -20, "CONDITIONAL",
     "Passed with a re-test of the data link range.", "نجاح مع إعادة اختبار مدى وصلة البيانات."),
    ("GS-003", "M005", "Golden sample all-terrain mobility trial", "تجربة الحركة في جميع التضاريس للعينة الذهبية", -5,
     "IN_PROGRESS", None, None),
    ("GS-004", "M009", "Golden sample sea-state 4 trial", "تجربة العينة الذهبية في حالة البحر 4", 25, "PLANNED", None, None),
)

# code, model, type, English, Arabic, benefit EN, benefit AR, status, complexity, cost, months, priority, project
DEVELOPMENT = (
    ("DEV-001", "M001", "COMMUNICATIONS", "Encrypted relay with network bonding", "ربط شبكي ومرحّل مشفر",
     "Extends the datalink to 200 km.", "يمد وصلة البيانات إلى 200 كم.", "IN_EXECUTION", "MEDIUM", 420_000, 6, "HIGH",
     "PRJ-004"),
    ("DEV-002", "M001", "AI", "Automatic target classification", "التصنيف الآلي للأهداف", "Cuts operator workload.",
     "يخفف عبء المشغل.", "POSSIBLE", "MEDIUM", 650_000, 9, "MEDIUM", None),
    ("DEV-003", "M001", "ENDURANCE", "Heavy-fuel engine", "محرك بالوقود الثقيل", "Adds 4 hours endurance.",
     "يضيف 4 ساعات تحمل.", "UNDER_STUDY", "HIGH", 1_800_000, 18, "MEDIUM", None),
    ("DEV-004", "M002", "AI", "Integrated detection upgrade", "ترقية الاكتشاف المدمج", "Detection range +40%.",
     "زيادة مدى الاكتشاف 40%.", "COMPLETED", "MEDIUM", 460_000, 8, "HIGH", "PRJ-014"),
    ("DEV-005", "M002", "SECURITY", "Anti-jamming navigation", "ملاحة مقاومة للتشويش", "Keeps navigation under jamming.",
     "يحافظ على الملاحة تحت التشويش.", "APPROVED", "LOW", 90_000, 3, "HIGH", None),
    ("DEV-006", "M003", "AI", "Swarm cooperative behaviours", "سلوكيات تعاونية للأسراب", "Coordinated area coverage.",
     "تغطية منسقة للمناطق.", "IN_EXECUTION", "HIGH", 3_200_000, 18, "HIGH", "PRJ-011"),
    ("DEV-007", "M003", "SENSORS", "Hyperspectral payload", "حمولة طيفية فائقة", "Material identification.",
     "تحديد المواد.", "POSSIBLE", "HIGH", 280_000, 5, "CRITICAL", None),
    ("DEV-008", "M004", "ENDURANCE", "High-capacity battery", "بطارية عالية السعة", "Night endurance 45 minutes.",
     "تحمل ليلي 45 دقيقة.", "UNDER_STUDY", "LOW", 60_000, 2, "MEDIUM", "PRJ-008"),
    ("DEV-009", "M005", "INTEGRATION", "Command and control integration", "التكامل مع القيادة والسيطرة",
     "Shared picture with headquarters.", "صورة موحدة مع القيادة.", "PROPOSED", "MEDIUM", 1_200_000, 12, "HIGH", None),
    ("DEV-010", "M006", "AUTONOMY", "SLAM navigation stack", "منظومة ملاحة SLAM", "GNSS-denied operation.",
     "تشغيل دون إشارات الملاحة.", "IN_EXECUTION", "HIGH", 1_500_000, 14, "HIGH", "PRJ-005"),
    ("DEV-011", "M006", "PAYLOAD", "Modular payload bay", "حجرة حمولات معيارية", "Swap payloads in 10 minutes.",
     "تبديل الحمولات خلال 10 دقائق.", "POSSIBLE", "LOW", 700_000, 6, "MEDIUM", None),
    ("DEV-012", "M007", "AUTONOMY", "Convoy follow-me", "اتباع القافلة", "One operator for four vehicles.",
     "مشغل واحد لأربع مركبات.", "UNDER_STUDY", "MEDIUM", 540_000, 10, "MEDIUM", "PRJ-009"),
    ("DEV-013", "M008", "AI", "Assisted manipulation", "التحكم المساعد بالذراع", "Faster render-safe procedures.",
     "إجراءات إبطال أسرع.", "PROPOSED", "HIGH", 380_000, 8, "HIGH", None),
    ("DEV-014", "M009", "SENSORS", "Thermal camera upgrade", "ترقية الكاميرا الحرارية", "Night detection at 5 km.",
     "اكتشاف ليلي حتى 5 كم.", "APPROVED", "LOW", 150_000, 4, "MEDIUM", None),
    ("DEV-015", "M012", "ENDURANCE", "Extended battery module", "وحدة بطارية ممتدة", "Endurance 40 hours.", "تحمل 40 ساعة.",
     "NOT_FEASIBLE", "HIGH", 0, 0, "LOW", None),
)
