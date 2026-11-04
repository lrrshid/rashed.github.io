"""Demonstration data shaped like the product brochure. Every name, manufacturer, supplier and figure is fictional.

Dates are day offsets from the day the demo is seeded, so delays, upcoming milestones and overdue items stay
meaningful whenever the demo is (re)built.
"""
from __future__ import annotations

# username, display name, role, department codes (DEPARTMENT-scoped roles only)
MOCK_USERS = (
    ("mock.admin", "Mock System Administrator", "SYS_ADMIN", ()),
    ("mock.exec", "Mock Executive", "EXECUTIVE", ()),
    ("mock.head", "Mock Head of Group 2", "DEPT_HEAD", ("G2",)),
    ("mock.capability", "Mock Capability Manager", "CAPABILITY_MGR", ()),
    ("mock.pm", "Mock Project Manager", "PROJECT_MGR", ()),
    ("mock.maint", "Mock Maintenance Lead", "MAINTENANCE", ()),
    ("mock.test", "Mock Test Lead", "TESTING", ()),
    ("mock.analyst", "Mock Analyst", "ANALYST", ()),
    ("mock.viewer", "Mock Viewer", "VIEWER", ()),
)

SITES = (
    ("NOB", "Northern Operations Base", "قاعدة العمليات الشمالية"),
    ("CTC", "Central Technical Centre", "المركز الفني المركزي"),
    ("ECS", "Eastern Coastal Station", "المحطة الساحلية الشرقية"),
    ("WSB", "Western Sector Base", "قاعدة القطاع الغربي"),
    ("TER", "Test and Evaluation Range", "ميدان التجارب والتقييم"),
)
# Where each department's assets are mostly kept.
DEPARTMENT_SITES = {"G1": ("CTC", "TER"), "G2": ("NOB", "WSB"), "G3": ("ECS", "NOB"), "G4": ("WSB", "ECS")}

# code, English, Arabic, kind, country EN, country AR
ORGANIZATIONS = (
    ("SAQR", "Saqr Aerial Technologies", "صقر للتقنيات الجوية", "MANUFACTURER", "United Arab Emirates", "الإمارات العربية المتحدة"),
    ("QASR", "Qasr Advanced Solutions", "قصر للحلول المتقدمة", "BOTH", "United Arab Emirates", "الإمارات العربية المتحدة"),
    ("HUDHUD", "Hudhud Drone Systems", "هدهد لأنظمة الطائرات المسيرة", "MANUFACTURER", "United Arab Emirates", "الإمارات العربية المتحدة"),
    ("ORION", "Orion Integrated Systems", "أوريون للأنظمة المتكاملة", "MANUFACTURER", "Italy", "إيطاليا"),
    ("DUNE", "Dune Robotics", "كثبان للروبوتات", "MANUFACTURER", "United Arab Emirates", "الإمارات العربية المتحدة"),
    ("DHOW", "Blue Dhow Marine Systems", "الداو الأزرق للأنظمة البحرية", "MANUFACTURER", "United Arab Emirates", "الإمارات العربية المتحدة"),
    ("DEEP", "Deep Wave Subsea", "الموجة العميقة للأنظمة تحت المائية", "MANUFACTURER", "Norway", "النرويج"),
    ("FALAJ", "Falaj Technical Support and Logistics", "فلج للدعم الفني واللوجستي", "SUPPLIER", "United Arab Emirates", "الإمارات العربية المتحدة"),
)

# code, English, Arabic, category, manufacturer, role EN, role AR, unit cost (AED), specs
MODELS = (
    ("M001", "Falcon-X", "فالكون-إكس", "UAV", "SAQR", "Fixed-wing reconnaissance", "استطلاع ثابت الجناح", 2_850_000,
     {"endurance": 14, "range": 180, "cruise_speed": 140, "ceiling": 4500, "payload": 18, "eo_ir": True,
      "night_vision": True, "sar": False, "payloads": "EO/IR gimbal, SAR pod, comms relay",
      "datalink": "Encrypted C-band LOS + SATCOM", "datalink_range": 180, "navigation": "Multi-GNSS + INS",
      "autonomy": "Waypoint + supervised autonomous return", "interoperability": "STANAG 4586 ground station",
      "ip_rating": "IP54", "operating_temp": "Max 50 °C ambient", "weather": "Moderate (light rain, dust)",
      "max_wind": 15}),
    ("M002", "Q4", "هدهد-Q4", "UAV", "HUDHUD", "Tactical quadcopter", "طائرة رباعية المراوح تكتيكية", 185_000,
     {"endurance": 0.8, "range": 8, "cruise_speed": 55, "ceiling": 1200, "payload": 1.2, "eo_ir": True,
      "night_vision": True, "datalink": "Encrypted 2.4/5.8 GHz", "datalink_range": 8, "navigation": "GNSS + visual",
      "autonomy": "Waypoint, follow-me", "ip_rating": "IP43", "max_wind": 12}),
    ("M003", "Sentinel VTOL", "ستنيل VTOL", "UAV", "ORION", "Vertical take-off long-range surveillance",
     "إقلاع وهبوط عمودي للمراقبة بعيدة المدى", 3_450_000,
     {"endurance": 10, "range": 150, "cruise_speed": 110, "ceiling": 4000, "payload": 12, "eo_ir": True,
      "night_vision": True, "sar": True, "datalink": "Encrypted LOS", "datalink_range": 150,
      "navigation": "RTK GNSS + INS", "autonomy": "Supervised autonomy", "ip_rating": "IP55", "max_wind": 14}),
    ("M004", "Shaheen Micro", "شاهين مايكرو", "UAV", "HUDHUD", "Small surveillance drone", "طائرة صغيرة للمراقبة",
     95_000, {"endurance": 0.6, "range": 5, "cruise_speed": 45, "payload": 0.4, "eo_ir": True, "night_vision": False,
              "datalink": "Encrypted 5.8 GHz", "datalink_range": 5, "ip_rating": "IP42", "max_wind": 10}),
    ("M005", "Sarab-L", "سراب-L", "UAV", "SAQR", "Long-endurance trials platform", "منصة تجارب طويلة التحمل",
     1_950_000, {"endurance": 18, "range": 220, "cruise_speed": 120, "ceiling": 5000, "payload": 25, "eo_ir": True,
                 "night_vision": True, "datalink": "SATCOM", "datalink_range": 400, "ip_rating": "IP54"}),
    ("M006", "Ranger-6", "رينجر-6", "UGV", "DUNE", "Ground reconnaissance vehicle", "مركبة برية للاستطلاع", 780_000,
     {"endurance": 8, "range": 40, "max_speed": 25, "payload": 150, "manipulator": False, "eo_ir": True,
      "night_vision": True, "datalink": "Mesh radio", "datalink_range": 3, "autonomy": "Teleoperation + waypoint",
      "terrain": "Desert, urban", "ip_rating": "IP66"}),
    ("M007", "Mule-T", "ميول-T", "UGV", "DUNE", "Multi-mission logistics vehicle", "مركبة لوجستية متعددة المهام",
     640_000, {"endurance": 10, "range": 60, "max_speed": 20, "payload": 500, "manipulator": False,
               "datalink": "Mesh radio", "terrain": "Desert", "ip_rating": "IP65"}),
    ("M008", "EOD Explorer", "مستكشف المتفجرات EOD", "UGV", "ORION", "Explosive ordnance disposal robot",
     "روبوت التعامل مع المتفجرات", 1_150_000,
     {"endurance": 4, "range": 1, "max_speed": 6, "payload": 30, "manipulator": True, "eo_ir": True,
      "night_vision": True, "datalink": "Fibre + radio", "ip_rating": "IP67", "terrain": "Urban, stairs"}),
    ("M009", "Wave Runner 7", "ويف رانر 7", "USV", "DHOW", "Rapid response and coastal patrol boat",
     "زورق استجابة سريعة ودوريات ساحلية", 2_250_000,
     {"endurance": 24, "range": 300, "max_speed": 40, "length": 7, "radar": True, "eo_ir": True, "night_vision": True,
      "datalink": "Encrypted LOS + 4G", "datalink_range": 40, "sea_state": 4, "ip_rating": "IP67"}),
    ("M010", "Sea Guard 12", "سي غارد 12", "USV", "DHOW", "Port patrol boat", "زورق دوريات الموانئ", 3_100_000,
     {"endurance": 36, "range": 450, "max_speed": 32, "length": 12, "radar": True, "eo_ir": True,
      "night_vision": True, "datalink": "SATCOM + LOS", "sea_state": 5, "ip_rating": "IP67"}),
    ("M011", "Rimora ROV", "ريمورا ROV", "UUV", "DEEP", "Underwater inspection vehicle", "مركبة فحص تحت مائية",
     890_000, {"endurance": 6, "max_depth": 300, "max_speed": 3, "sonar": "Imaging sonar",
               "datalink": "Tether", "water_temp": "0–40 °C"}),
    ("M012", "Deep Fin AUV", "ديب فين AUV", "UUV", "DEEP", "Autonomous deep-water survey", "مسح ذاتي للمياه العميقة",
     4_200_000, {"endurance": 30, "max_depth": 1500, "max_speed": 4, "sonar": "Side-scan + multibeam",
                 "datalink": "Acoustic modem", "autonomy": "Fully autonomous mission"}),
)

# Asset status letters used below.
STATUS_LETTERS = {"R": "READY", "L": "READY_LIMITED", "T": "TEMP_NOT_READY", "M": "UNDER_MAINTENANCE",
                  "N": "NOT_READY", "P": "AWAITING_REPLACEMENT", "W": "WRITTEN_OFF", "A": "UNDER_ACQUISITION",
                  "D": "UNDER_DEVELOPMENT", "X": "UNDER_TEST"}

# code, English, Arabic, department, category, required, priority, model codes, assets (one status letter each)
REQUIREMENTS = (
    ("RQ01", "Wide-area reconnaissance aircraft", "طائرات الاستطلاع واسع النطاق", "G2", "UAV", 15, "CRITICAL",
     ("M001",), "RRRRRRLMTNPWAAAD"),
    ("RQ02", "Robotic explosive-ordnance platforms", "منصات التعامل مع المتفجرات الروبوتية", "G3", "UGV", 3,
     "CRITICAL", ("M008",), "RN"),
    ("RQ03", "Port patrol boats", "زوارق دوريات الموانئ", "G3", "USV", 3, "CRITICAL", ("M010",), "RR"),
    ("RQ04", "Tactical quadcopters", "الطائرات رباعية المراوح التكتيكية", "G3", "UAV", 8, "HIGH", ("M002",),
     "RRRRMN"),
    ("RQ05", "Public-event surveillance drones", "طائرات مراقبة الفعاليات العامة", "G2", "UAV", 10, "HIGH",
     ("M004",), "RRRRRLMA"),
    ("RQ06", "Ground reconnaissance vehicles", "المركبات البرية للاستطلاع", "G2", "UGV", 5, "HIGH", ("M006",),
     "RRRTP"),
    ("RQ07", "Multi-mission tactical ground vehicles", "المركبات البرية التكتيكية متعددة المهام", "G4", "UGV", 3,
     "HIGH", ("M007",), "RRP"),
    ("RQ08", "Rapid response boats", "زوارق الاستجابة السريعة", "G4", "USV", 3, "MEDIUM", ("M009",), "RX"),
    ("RQ09", "Small surveillance drones", "الطائرات الصغيرة للمراقبة", "G4", "UAV", 6, "MEDIUM", ("M004", "M002"),
     "RRRRMXN"),
    ("RQ10", "Coastal surveillance boats", "زوارق المراقبة الساحلية", "G2", "USV", 4, "MEDIUM", ("M009",), "RRLT"),
    ("RQ11", "Aircraft trials and evaluation fleet", "أسطول تجارب وتقييم الطائرات", "G1", "UAV", 4, "MEDIUM",
     ("M003", "M005"), "RRXX"),
    ("RQ12", "Deep-water autonomous research vehicles", "أبحاث المركبات الذاتية للمياه العميقة", "G1", "UUV", 2,
     "LOW", ("M012",), "D"),
    ("RQ13", "Underwater infrastructure inspection", "مركبات فحص البنية تحت المائية", "G3", "UUV", 2, "MEDIUM",
     ("M011",), "RM"),
    ("RQ14", "Autonomy test platforms", "منصات اختبار الاستقلالية", "G1", "UGV", 2, "LOW", ("M006",), "RA"),
    ("RQ15", "Coastal underwater survey", "المسح الساحلي تحت الماء", "G4", "UUV", 2, "LOW", ("M011",), "AA"),
)

# code, English, Arabic, supplier, value, start offset, end offset
CONTRACTS = (
    ("CT-2021-008", "Falcon-X initial supply", "توريد الأسطول الأولي لفالكون-إكس", "QASR", 34_000_000, -1900, -400),
    ("CT-2025-003", "Falcon-X airframe replacement", "استبدال هياكل فالكون-إكس", "QASR", 3_100_000, -270, 120),
    ("CT-2024-011", "Q4 quadcopter supply", "توريد الطائرات رباعية المراوح Q4", "HUDHUD", 1_480_000, -700, -200),
    ("CT-2023-005", "Ranger-6 vehicles and support", "مركبات رينجر-6 والدعم", "DUNE", 5_200_000, -1100, 300),
    ("CT-2022-014", "Marine systems framework", "الإطار التعاقدي للأنظمة البحرية", "DHOW", 18_500_000, -1500, 500),
    ("CT-2026-002", "Wide-area reconnaissance expansion", "توسعة أسطول الاستطلاع واسع النطاق", "QASR", 12_500_000,
     -60, 420),
)
# model code -> contract code assets of that model were bought under
MODEL_CONTRACTS = {"M001": "CT-2021-008", "M002": "CT-2024-011", "M006": "CT-2023-005", "M009": "CT-2022-014",
                   "M010": "CT-2022-014"}

PEOPLE = ("Lt. Col. Khalid Al Mansoori", "Maj. Salem Al Ketbi", "Capt. Hamad Al Nuaimi", "Maj. Eng. Fatima Al Shamsi",
          "Maj. Rashid Al Suwaidi", "Lt. Col. Dr. Aisha Al Kaabi", "Maj. Eng. Omar Al Dhaheri",
          "Maj. Eng. Noora Al Falasi", "Capt. Mariam Al Hosani")

# code, English, Arabic, type, department, category, status, manager index, start, target end, forecast end,
# progress, budget, committed, spend, supplier, contract, requirement links ((code, qty),), model links ((code, rel),),
# next action EN, next action AR
PROJECTS = (
    ("PRJ-001", "Wide-area reconnaissance fleet expansion", "توسعة أسطول الاستطلاع واسع النطاق", "NEW_ACQUISITION",
     "G2", "UAV", "CONTRACTING", 1, -400, 420, 450, 38, 12_500_000, 6_000_000, 3_100_000, "QASR", "CT-2026-002",
     (("RQ01", 6),), (("M001", "CREATE"),),
     "Close the contract negotiation and confirm the delivery schedule.", "إنهاء مفاوضات العقد وتأكيد جدول التسليم."),
    ("PRJ-002", "Tactical quadcopter procurement, batch 2", "شراء أسطول الطائرات رباعية المراوح — الدفعة الثانية",
     "NEW_ACQUISITION", "G3", "UAV", "PROCUREMENT", 7, -200, 190, 190, 30, 4_200_000, 2_100_000, 900_000, "HUDHUD",
     None, (("RQ04", 3),), (("M002", "CREATE"),),
     "Evaluate the three received offers.", "تقييم العروض الثلاثة المستلمة."),
    ("PRJ-003", "Robotic explosive-ordnance capability increase", "زيادة قدرة منصات التعامل مع المتفجرات",
     "NEW_ACQUISITION", "G3", "UGV", "UNDER_STUDY", 6, -60, 500, 520, 10, 3_000_000, 0, 200_000, None, None,
     (("RQ02", 2),), (("M008", "CREATE"),),
     "Finish the requirements study and request approval.", "استكمال دراسة المتطلبات وطلب الاعتماد."),
    ("PRJ-004", "Falcon-X second-version evaluation", "تقييم فالكون-إكس الإصدار الثاني", "TRIALS", "G2", "UAV",
     "EVALUATION", 2, -260, 45, 45, 70, 900_000, 500_000, 450_000, "SAQR", None, (("RQ05", 3),),
     (("M001", "UPGRADE"),), "Complete the evaluation report.", "استكمال تقرير التقييم."),
    ("PRJ-005", "Ranger-6 autonomy upgrade", "ترقية الاستقلالية لرينجر-6", "UPGRADE", "G1", "UGV", "DEVELOPMENT", 4,
     -300, 220, 248, 55, 2_100_000, 1_400_000, 1_200_000, "DUNE", "CT-2023-005", (("RQ06", 1), ("RQ14", 1)),
     (("M006", "UPGRADE"),), "Integrate the new navigation stack.", "دمج منظومة الملاحة الجديدة."),
    ("PRJ-006", "Falcon-X airframe replacement programme", "برنامج استبدال هياكل فالكون-إكس", "REPLACEMENT", "G2",
     "UAV", "MANUFACTURING", 0, -270, 56, 70, 62, 3_100_000, 850_000, 1_950_000, "QASR", "CT-2025-003", (),
     (("M001", "REPLACE"),), "Reschedule the factory acceptance test with the manufacturer.",
     "إعادة جدولة اختبار القبول في المصنع مع الشركة المصنعة."),
    ("PRJ-007", "Wave Runner coastal trials", "تجارب زورق ويف رانر الساحلي", "TRIALS", "G2", "USV", "FIELD_TRIALS", 4,
     -150, 20, 40, 75, 600_000, 100_000, 500_000, "DHOW", None, (("RQ10", 0),), (("M009", "UPGRADE"),),
     "Re-plan the sea trial lost to weather.", "إعادة تخطيط التجربة البحرية الملغاة بسبب الطقس."),
    ("PRJ-008", "Shaheen Micro field evaluation", "التقييم الميداني لطائرة شاهين مايكرو", "TRIALS", "G4", "UAV",
     "TESTING", 8, -100, 60, 60, 60, 350_000, 50_000, 200_000, "HUDHUD", None, (("RQ09", 1),),
     (("M004", "UPGRADE"),), "Run the night-time endurance series.", "تنفيذ سلسلة اختبارات التحمل الليلي."),
    ("PRJ-009", "Multi-mission ground vehicle concept study", "دراسة مفهوم المركبة البرية متعددة المهام", "RND",
     "G4", "UGV", "PROPOSED", 5, -30, 700, 700, 0, 500_000, 0, 0, None, None, (("RQ07", 1),), (),
     "Present the concept to the steering committee.", "عرض المفهوم على اللجنة التوجيهية."),
    ("PRJ-010", "Rapid response boat acquisition", "اقتناء زوارق الاستجابة السريعة", "NEW_ACQUISITION", "G4", "USV",
     "APPROVED", 2, -40, 380, 380, 15, 5_500_000, 2_000_000, 600_000, "DHOW", "CT-2022-014", (("RQ08", 2),),
     (("M009", "CREATE"),), "Issue the call-off order under the framework contract.",
     "إصدار أمر الشراء بموجب العقد الإطاري."),
    ("PRJ-011", "Autonomous swarm coordination prototype", "نموذج توضيحي لتنسيق الأسراب الذاتية", "AI_ENHANCEMENT",
     "G1", "UAV", "DEVELOPMENT", 5, -330, 150, 225, 45, 1_800_000, 900_000, 1_050_000, "ORION", None,
     (("RQ11", 2),), (("M003", "UPGRADE"), ("M005", "UPGRADE")),
     "Fix the swarm deconfliction defects found in simulation.", "معالجة عيوب فض التعارض المكتشفة في المحاكاة."),
    ("PRJ-012", "Deep-water autonomous vehicle proof of concept", "إثبات مفهوم المركبة الذاتية للمياه العميقة",
     "RND", "G1", "UUV", "DEVELOPMENT", 6, -400, 120, 160, 40, 2_600_000, 1_000_000, 1_500_000, "DEEP", None,
     (("RQ12", 2),), (("M012", "CREATE"),),
     "Repeat the pressure-housing qualification.", "إعادة تأهيل غلاف الضغط."),
    ("PRJ-013", "AI integration for predictive maintenance", "دمج الذكاء الاصطناعي للصيانة التنبؤية",
     "AI_ENHANCEMENT", "G1", "UAV", "TESTING", 3, -280, 25, 25, 85, 1_200_000, 200_000, 1_000_000, "QASR", None, (),
     (("M001", "UPGRADE"),), "Validate the model against six months of fault data.",
     "التحقق من النموذج مقابل بيانات أعطال ستة أشهر."),
    ("PRJ-014", "Q4 integrated detection upgrade", "ترقية الاكتشاف المدمج لهدهد-Q4", "UPGRADE", "G3", "UAV",
     "COMPLETED", 2, -500, -40, -35, 100, 800_000, 0, 780_000, "HUDHUD", "CT-2024-011", (), (("M002", "UPGRADE"),),
     "Closed.", "مغلق."),
)
# stage names (English) that are major milestones
MAJOR_STAGES = {"Approval", "Contracting", "Factory acceptance test", "Delivery", "Acceptance", "Field trials",
                "Evaluation", "Proof of concept", "Decision", "Testing", "Report and recommendation"}

# project code -> {dimension: (rag, reason EN, reason AR)}
HEALTH_NOTES = {
    "PRJ-001": {"PROCUREMENT": ("AMBER", "Contract negotiation 45 days behind plan.", "مفاوضات العقد متأخرة 45 يوماً عن الخطة.")},
    "PRJ-006": {"PROCUREMENT": ("AMBER", "Composite material delivery delayed at the manufacturer.",
                                "تأخر توريد المواد المركبة لدى الشركة المصنعة."),
                "SCOPE": ("GREEN", "Scope unchanged since approval.", "النطاق دون تغيير منذ الاعتماد.")},
    "PRJ-011": {"SCOPE": ("AMBER", "Swarm size increased from 6 to 8 aircraft.", "زيادة حجم السرب من 6 إلى 8 طائرات.")},
    "PRJ-012": {"SCOPE": ("RED", "Depth requirement raised from 1,000 m to 1,500 m.", "رفع متطلب العمق من 1000 م إلى 1500 م.")},
}

# code, project, English, Arabic, category, probability, impact, owner index, mitigation EN, mitigation AR,
# mitigation due offset, status
RISKS = (
    ("RSK-001", "PRJ-001", "Supplier may not meet contractual delivery dates.", "قد لا يلتزم المورد بمواعيد التسليم التعاقدية.",
     "COMMERCIAL", 4, 4, 0, "Weekly supplier progress reviews.", "مراجعات أسبوعية لتقدم المورد.", 13, "OPEN"),
    ("RSK-002", "PRJ-001", "Export licence for the SAR pod may be delayed.", "قد يتأخر ترخيص تصدير حاضنة الرادار.",
     "REGULATORY", 3, 5, 1, "Parallel request through the government channel.", "طلب موازٍ عبر القناة الحكومية.", 30, "OPEN"),
    ("RSK-003", "PRJ-002", "Received offers may exceed the approved budget.", "قد تتجاوز العروض المستلمة الميزانية المعتمدة.",
     "FINANCIAL", 3, 4, 3, "Prepare a reduced-scope option.", "إعداد خيار بنطاق مخفض.", -5, "MITIGATING"),
    ("RSK-004", "PRJ-005", "New navigation stack may not reach 95% accuracy.", "قد لا تصل منظومة الملاحة الجديدة إلى دقة 95%.",
     "TECHNICAL", 3, 4, 6, "Add a visual-odometry fallback.", "إضافة نظام احتياطي للقياس البصري.", 15, "OPEN"),
    ("RSK-005", "PRJ-006", "Composite material shortage at the manufacturer.", "نقص المواد المركبة لدى الشركة المصنعة.",
     "SUPPLY_CHAIN", 4, 4, 0, "Approve a second material source.", "اعتماد مصدر ثانٍ للمواد.", -12, "OPEN"),
    ("RSK-006", "PRJ-007", "Seasonal weather may cancel further sea trials.", "قد يلغي الطقس الموسمي تجارب بحرية أخرى.",
     "ENVIRONMENTAL", 4, 3, 4, "Book a reserve trial window.", "حجز نافذة تجارب احتياطية.", -3, "OPEN"),
    ("RSK-007", "PRJ-011", "Swarm deconfliction may fail at scale.", "قد يفشل فض التعارض في الأسراب الكبيرة.",
     "TECHNICAL", 5, 5, 5, "Staged scaling with simulation gates.", "توسع تدريجي مع بوابات محاكاة.", 8, "OPEN"),
    ("RSK-008", "PRJ-011", "AI component cost growth.", "ارتفاع تكلفة مكونات الذكاء الاصطناعي.",
     "FINANCIAL", 4, 4, 5, "Freeze the hardware baseline.", "تجميد خط الأساس للأجهزة.", 20, "MITIGATING"),
    ("RSK-009", "PRJ-012", "Pressure housing may fail qualification again.", "قد يفشل غلاف الضغط في التأهيل مجدداً.",
     "TECHNICAL", 2, 4, 7, "Independent design review.", "مراجعة تصميم مستقلة.", 45, "OPEN"),
    ("RSK-010", "PRJ-013", "The manufacturer may not share the needed telemetry data.",
     "قد لا تشارك الشركة المصنعة بيانات القياس عن بعد المطلوبة.", "COMMERCIAL", 3, 5, 6,
     "Data-sharing clause in the support contract.", "بند مشاركة البيانات في عقد الدعم.", -8, "OPEN"),
    ("RSK-011", "PRJ-010", "Framework contract ceiling may be reached.", "قد يتم بلوغ سقف العقد الإطاري.",
     "COMMERCIAL", 2, 3, 2, "Monitor call-off values monthly.", "متابعة قيم أوامر الشراء شهرياً.", 60, "OPEN"),
    ("RSK-012", "PRJ-008", "Night endurance below the 40-minute target.", "قد يقل التحمل الليلي عن هدف 40 دقيقة.",
     "TECHNICAL", 3, 3, 8, "Test the high-capacity battery pack.", "اختبار حزمة البطارية عالية السعة.", 10, "OPEN"),
    ("RSK-013", "PRJ-003", "Requirement may change after the threat review.", "قد يتغير المتطلب بعد مراجعة التهديدات.",
     "OPERATIONAL", 2, 2, 6, "Keep the study modular.", "إبقاء الدراسة مرنة وقابلة للتجزئة.", 40, "OPEN"),
    ("RSK-014", "PRJ-014", "Upgrade documentation incomplete.", "توثيق الترقية غير مكتمل.",
     "OPERATIONAL", 1, 2, 2, "Collect documents at closure.", "جمع المستندات عند الإغلاق.", -50, "CLOSED"),
)

# code, project, English, Arabic, severity, owner index, raised offset, target offset, escalated, status,
# resolution EN, resolution AR
ISSUES = (
    ("ISS-001", "PRJ-006", "Factory acceptance test postponed: composite material shortage.",
     "تأجيل اختبار القبول في المصنع بسبب نقص المواد المركبة.", "HIGH", 0, -20, 14, True, "OPEN", None, None),
    ("ISS-002", "PRJ-011", "Simulation shows swarm conflicts above six aircraft.",
     "تظهر المحاكاة تعارضات في السرب لأكثر من ست طائرات.", "CRITICAL", 5, -35, 7, True, "OPEN", None, None),
    ("ISS-003", "PRJ-007", "Sea trial cancelled: weather window lost; trial must be re-planned.",
     "إلغاء التجربة البحرية لفقدان نافذة الطقس؛ يلزم إعادة التخطيط.", "HIGH", 4, -10, 10, False, "IN_PROGRESS", None, None),
    ("ISS-004", "PRJ-004", "Ground station software crash during evaluation.",
     "تعطل برنامج المحطة الأرضية أثناء التقييم.", "MEDIUM", 6, -15, -2, False, "IN_PROGRESS", None, None),
    ("ISS-005", "PRJ-005", "Navigation sensor delivery late by three weeks.", "تأخر توريد حساس الملاحة ثلاثة أسابيع.",
     "MEDIUM", 6, -40, -10, False, "RESOLVED", "Supplier air-freighted the sensors.", "شحن المورد الحساسات جواً."),
    ("ISS-006", "PRJ-013", "Telemetry format differs between aircraft batches.",
     "اختلاف صيغة بيانات القياس بين دفعات الطائرات.", "HIGH", 6, -25, 5, True, "AWAITING_DECISION", None, None),
    ("ISS-007", "PRJ-001", "Liquidated-damages clause disputed by the supplier.", "اعتراض المورد على بند غرامات التأخير.",
     "HIGH", 0, -18, 12, False, "OPEN", None, None),
    ("ISS-008", "PRJ-012", "Test tank booking conflict.", "تعارض في حجز حوض الاختبار.", "LOW", 7, -8, 20, False,
     "OPEN", None, None),
    ("ISS-009", "PRJ-002", "One bidder requests a two-week extension.", "طلب أحد المتقدمين تمديداً لمدة أسبوعين.",
     "LOW", 7, -12, -2, False, "CLOSED", "Extension refused; offers evaluated as received.",
     "رُفض التمديد؛ وقُيّمت العروض كما وردت."),
)
