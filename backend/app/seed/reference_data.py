"""Reference data every installation starts with (demo and Oracle alike): roles and their permissions, status lists,
project types and their workflow stages, technical specification fields, AI technologies and the business-rule
defaults. All of it is editable afterwards in Settings; the seeders only add what is missing."""
from __future__ import annotations

ALL_PERMISSIONS = ("view", "edit.requirements", "edit.models", "edit.assets", "edit.projects", "edit.risks",
                   "edit.maintenance", "edit.testing", "edit.documents", "reports.view", "reports.exec",
                   "reports.build", "reports.schedule", "export", "admin")

# code, English, Arabic, scope, permissions
ROLES = (
    ("SYS_ADMIN", "System administrator", "مدير النظام", "ALL", ALL_PERMISSIONS),
    ("EXECUTIVE", "Executive leadership", "القيادة التنفيذية", "ALL",
     ("view", "reports.view", "reports.exec", "export")),
    ("DEPT_HEAD", "Head of department", "رئيس الإدارة", "DEPARTMENT",
     ("view", "edit.requirements", "reports.view", "reports.exec", "export")),
    ("CAPABILITY_MGR", "Capability manager", "مدير القدرات", "ALL",
     ("view", "edit.requirements", "edit.models", "edit.assets", "edit.documents", "reports.view", "reports.exec",
      "reports.build", "export")),
    ("PROJECT_MGR", "Project manager", "مدير المشروع", "ALL",
     ("view", "edit.projects", "edit.risks", "edit.documents", "reports.view", "export")),
    ("MAINTENANCE", "Maintenance team", "فريق الصيانة", "ALL",
     ("view", "edit.maintenance", "edit.documents", "reports.view")),
    ("TESTING", "Testing team", "فريق التجارب", "ALL",
     ("view", "edit.testing", "edit.documents", "reports.view")),
    ("ANALYST", "Analyst", "محلل", "ALL",
     ("view", "reports.view", "reports.exec", "reports.build", "reports.schedule", "export")),
    ("VIEWER", "Viewer", "مطّلع", "ALL", ("view", "reports.view")),
)

# domain -> (code, English, Arabic, colour, terminal)
STATUSES = {
    "ASSET": (
        ("READY", "Ready for operations", "جاهز للعمليات", "green", 0),
        ("READY_LIMITED", "Ready with limitations", "جاهز مع قيود", "teal", 0),
        ("TEMP_NOT_READY", "Temporarily not ready", "غير جاهز مؤقتاً", "amber", 0),
        ("UNDER_MAINTENANCE", "Under maintenance", "قيد الصيانة", "orange", 0),
        ("NOT_READY", "Not ready", "غير جاهز", "red", 0),
        ("AWAITING_REPLACEMENT", "Awaiting replacement", "بانتظار الاستبدال", "purple", 0),
        ("UNDER_ACQUISITION", "Under acquisition", "قيد الاقتناء", "blue", 0),
        ("UNDER_DEVELOPMENT", "Under development", "قيد التطوير", "pink", 0),
        ("UNDER_TEST", "Under test", "قيد الاختبار", "dark", 0),
        ("WRITTEN_OFF", "Written off", "مشطوب", "grey", 1),
    ),
    "PROJECT": (
        ("PROPOSED", "Proposed", "مقترح", "grey", 0),
        ("UNDER_STUDY", "Under study", "قيد الدراسة", "orange", 0),
        ("APPROVED", "Approved", "معتمد", "teal", 0),
        ("PROCUREMENT", "Procurement", "قيد الشراء", "amber", 0),
        ("CONTRACTING", "Contracting", "قيد التعاقد", "pink", 0),
        ("DEVELOPMENT", "Development", "قيد التطوير", "green", 0),
        ("MANUFACTURING", "Manufacturing", "قيد التصنيع", "purple", 0),
        ("TESTING", "Testing", "قيد الاختبار", "red", 0),
        ("FIELD_TRIALS", "Field trials", "التجارب الميدانية", "blue", 0),
        ("EVALUATION", "Evaluation", "قيد التقييم", "red", 0),
        ("COMPLETED", "Completed", "مكتمل", "green", 1),
        ("ON_HOLD", "On hold", "معلق", "amber", 0),
        ("CANCELLED", "Cancelled", "ملغى", "grey", 1),
    ),
    "MILESTONE": (
        ("NOT_STARTED", "Not started", "لم يبدأ", "grey", 0),
        ("IN_PROGRESS", "In progress", "قيد التنفيذ", "blue", 0),
        ("DELAYED", "Delayed", "متأخر", "red", 0),
        ("COMPLETED", "Completed", "مكتمل", "green", 1),
    ),
    "RISK": (
        ("OPEN", "Open", "مفتوحة", "red", 0),
        ("MITIGATING", "Being mitigated", "قيد المعالجة", "amber", 0),
        ("CLOSED", "Closed", "مغلقة", "grey", 1),
    ),
    "ISSUE": (
        ("OPEN", "Open", "مفتوحة", "red", 0),
        ("IN_PROGRESS", "In progress", "قيد المعالجة", "blue", 0),
        ("AWAITING_DECISION", "Awaiting decision", "بانتظار قرار", "amber", 0),
        ("RESOLVED", "Resolved", "تم حلها", "green", 1),
        ("CLOSED", "Closed", "مغلقة", "grey", 1),
    ),
    "TEST": (
        ("PLANNED", "Planned", "مخطط", "grey", 0),
        ("IN_PROGRESS", "In progress", "قيد التنفيذ", "blue", 0),
        ("AWAITING_RESULT", "Awaiting result", "بانتظار النتيجة", "amber", 0),
        ("PASSED", "Passed", "ناجح", "green", 1),
        ("CONDITIONAL", "Conditional pass", "نجاح مشروط", "amber", 1),
        ("FAILED", "Failed", "راسب", "red", 1),
        ("CANCELLED", "Cancelled", "ملغى", "grey", 1),
    ),
    "MAINTENANCE": (
        ("PLANNED", "Planned", "مخططة", "grey", 0),
        ("IN_PROGRESS", "In progress", "قيد التنفيذ", "blue", 0),
        ("AWAITING_PARTS", "Awaiting spare parts", "بانتظار قطع الغيار", "amber", 0),
        ("COMPLETED", "Completed", "مكتملة", "green", 1),
        ("CANCELLED", "Cancelled", "ملغاة", "grey", 1),
    ),
    "DEVELOPMENT": (
        ("PROPOSED", "Proposed", "مقترح", "grey", 0),
        ("POSSIBLE", "Possible", "ممكن", "blue", 0),
        ("UNDER_STUDY", "Under study", "قيد الدراسة", "amber", 0),
        ("APPROVED", "Approved", "معتمد", "teal", 0),
        ("IN_EXECUTION", "In execution", "قيد التنفيذ", "purple", 0),
        ("COMPLETED", "Completed", "مكتمل", "green", 1),
        ("NOT_FEASIBLE", "Not feasible", "غير ممكن", "red", 1),
    ),
}

_ACQ = (
    ("Concept", "المفهوم"), ("Requirements definition", "تحديد المتطلبات"), ("Market study", "دراسة السوق"),
    ("Approval", "الاعتماد"), ("Procurement", "الشراء"), ("Contracting", "التعاقد"), ("Manufacturing", "التصنيع"),
    ("Factory acceptance test", "اختبار القبول في المصنع"), ("Delivery", "التسليم"),
    ("Internal trials", "التجارب الداخلية"), ("Acceptance", "القبول"), ("Training", "التدريب"),
    ("Initial operation", "التشغيل الأولي"), ("Project closure", "إغلاق المشروع"),
)
_UPGRADE = (
    ("Concept", "المفهوم"), ("Technical study", "الدراسة الفنية"), ("Approval", "الاعتماد"),
    ("Development", "التطوير"), ("Integration", "التكامل"), ("Testing", "الاختبار"),
    ("Field trials", "التجارب الميدانية"), ("Acceptance", "القبول"), ("Rollout", "التعميم"),
    ("Project closure", "إغلاق المشروع"),
)
_TRIALS = (
    ("Test planning", "تخطيط التجارب"), ("Preparation", "التحضير"), ("Internal trials", "التجارب الداخلية"),
    ("Field trials", "التجارب الميدانية"), ("Evaluation", "التقييم"), ("Report and recommendation", "التقرير والتوصية"),
)
_RND = (
    ("Concept", "المفهوم"), ("Research", "البحث"), ("Prototype", "النموذج الأولي"),
    ("Proof of concept", "إثبات المفهوم"), ("Evaluation", "التقييم"), ("Decision", "القرار"),
)

# code, English, Arabic, colour, stages
PROJECT_TYPES = (
    ("NEW_ACQUISITION", "New acquisition", "اقتناء جديد", "blue", _ACQ),
    ("REPLACEMENT", "Replacement project", "مشروع استبدال", "orange", _ACQ),
    ("UPGRADE", "Upgrade of an existing capability", "ترقية قدرة قائمة", "teal", _UPGRADE),
    ("AI_ENHANCEMENT", "AI enhancement", "تعزيز الذكاء الاصطناعي", "purple", _UPGRADE),
    ("TRIALS", "Trials and evaluation", "التجارب والتقييم", "amber", _TRIALS),
    ("RND", "Development / research / proof of concept", "تطوير / بحث / إثبات مفهوم", "pink", _RND),
)

DEPARTMENTS = (("G1", "Group 1", "مجموعة 1"), ("G2", "Group 2", "مجموعة 2"), ("G3", "Group 3", "مجموعة 3"),
               ("G4", "Group 4", "مجموعة 4"))

CATEGORIES = (
    ("UAV", "Unmanned aerial vehicles", "المركبات الجوية غير المأهولة"),
    ("UGV", "Unmanned ground vehicles", "المركبات البرية غير المأهولة"),
    ("USV", "Unmanned surface vessels", "الزوارق السطحية غير المأهولة"),
    ("UUV", "Unmanned underwater vehicles", "المركبات تحت المائية غير المأهولة"),
)

# category code -> (section, code, English, Arabic, unit, type)
_COMMON_TAIL = (
    ("SENSORS", "eo_ir", "EO/IR camera", "كاميرا كهروبصرية / حرارية", None, "BOOL"),
    ("SENSORS", "night_vision", "Night operation", "التشغيل الليلي", None, "BOOL"),
    ("SENSORS", "payloads", "Payload options", "خيارات الحمولة", None, "TEXT"),
    ("COMMUNICATIONS", "datalink", "Datalink", "وصلة البيانات", None, "TEXT"),
    ("COMMUNICATIONS", "datalink_range", "Datalink range", "مدى وصلة البيانات", "km", "NUMBER"),
    ("COMMUNICATIONS", "navigation", "Navigation", "الملاحة", None, "TEXT"),
    ("COMMUNICATIONS", "autonomy", "Autonomy mode", "نمط الاستقلالية", None, "TEXT"),
    ("COMMUNICATIONS", "interoperability", "Interoperability", "التوافق التشغيلي", None, "TEXT"),
    ("ENVIRONMENT", "ip_rating", "Ingress protection", "درجة الحماية", None, "TEXT"),
    ("ENVIRONMENT", "operating_temp", "Operating temperature", "درجة حرارة التشغيل", None, "TEXT"),
    ("ENVIRONMENT", "weather", "Weather limits", "حدود الطقس", None, "TEXT"),
)
SPEC_FIELDS = {
    "UAV": (
        ("PERFORMANCE", "endurance", "Endurance", "مدة التحليق", "h", "NUMBER"),
        ("PERFORMANCE", "range", "Range", "المدى", "km", "NUMBER"),
        ("PERFORMANCE", "cruise_speed", "Cruise speed", "سرعة التطواف", "km/h", "NUMBER"),
        ("PERFORMANCE", "ceiling", "Service ceiling", "ارتفاع التشغيل", "m", "NUMBER"),
        ("PERFORMANCE", "payload", "Payload", "الحمولة", "kg", "NUMBER"),
        ("SENSORS", "sar", "Synthetic aperture radar", "رادار ذو فتحة اصطناعية", None, "BOOL"),
        *_COMMON_TAIL,
        ("ENVIRONMENT", "max_wind", "Maximum wind", "أقصى سرعة رياح", "m/s", "NUMBER"),
    ),
    "UGV": (
        ("PERFORMANCE", "endurance", "Endurance", "مدة التشغيل", "h", "NUMBER"),
        ("PERFORMANCE", "range", "Range", "المدى", "km", "NUMBER"),
        ("PERFORMANCE", "max_speed", "Maximum speed", "السرعة القصوى", "km/h", "NUMBER"),
        ("PERFORMANCE", "payload", "Payload", "الحمولة", "kg", "NUMBER"),
        ("PERFORMANCE", "manipulator", "Manipulator arm", "الذراع الآلية", None, "BOOL"),
        *_COMMON_TAIL,
        ("ENVIRONMENT", "terrain", "Terrain", "التضاريس", None, "TEXT"),
    ),
    "USV": (
        ("PERFORMANCE", "endurance", "Endurance", "مدة الإبحار", "h", "NUMBER"),
        ("PERFORMANCE", "range", "Range", "المدى", "nm", "NUMBER"),
        ("PERFORMANCE", "max_speed", "Maximum speed", "السرعة القصوى", "kn", "NUMBER"),
        ("PERFORMANCE", "length", "Length", "الطول", "m", "NUMBER"),
        ("SENSORS", "radar", "Marine radar", "رادار بحري", None, "BOOL"),
        *_COMMON_TAIL,
        ("ENVIRONMENT", "sea_state", "Maximum sea state", "أقصى حالة بحر", None, "NUMBER"),
    ),
    "UUV": (
        ("PERFORMANCE", "endurance", "Endurance", "مدة الغوص", "h", "NUMBER"),
        ("PERFORMANCE", "max_depth", "Maximum depth", "أقصى عمق", "m", "NUMBER"),
        ("PERFORMANCE", "max_speed", "Maximum speed", "السرعة القصوى", "kn", "NUMBER"),
        ("SENSORS", "sonar", "Sonar", "السونار", None, "TEXT"),
        *_COMMON_TAIL,
        ("ENVIRONMENT", "water_temp", "Water temperature", "حرارة الماء", None, "TEXT"),
    ),
}

# Business rules (services/settings_service.py reads them; Settings > Business rules edits them).
SETTINGS = {
    # Asset statuses that count as available (completion, gaps) and as operational.
    "assets.available_statuses": ["READY", "READY_LIMITED", "TEMP_NOT_READY", "UNDER_MAINTENANCE"],
    "assets.operational_statuses": ["READY", "READY_LIMITED"],
    # Assets on their way: counted as pipeline, never as available.
    "assets.pipeline_statuses": ["UNDER_ACQUISITION", "UNDER_DEVELOPMENT", "UNDER_TEST"],
    # Project statuses whose quantities count toward the forecast completion.
    "projects.forecast_statuses": ["APPROVED", "PROCUREMENT", "CONTRACTING", "DEVELOPMENT", "MANUFACTURING",
                                   "TESTING", "FIELD_TRIALS", "EVALUATION"],
    # Schedule health: days late (forecast or today past the target) at which a project turns amber / red.
    "health.schedule": {"amber_days": 1, "red_days": 30},
    # Budget health: spend + commitments over budget, in percent, at which a project turns amber / red.
    "health.budget": {"amber_pct": 0, "red_pct": 10},
    # Risk scores (probability x impact) that make a risk critical / high / medium.
    "health.risk": {"critical": 15, "high": 10, "medium": 5},
    # Readiness: the overall figure is a weighted average of the four dimensions (weights in percent).
    "readiness.weights": {"operational": 40, "technical": 30, "mission": 20, "maintenance": 10},
    # Assets older than this many years are flagged for replacement in decision support.
    "assets.replacement_age_years": 3.8,
    # Printed in every report header.
    "reports.classification": {"en": "Classification: to be set later", "ar": "التصنيف: يحدد لاحقاً"},
}

# AI technologies (Settings > AI capability levels edits them) and the level criteria L1-L5.
AI_TECHNOLOGIES = (
    ("COMPUTER_VISION", "Computer vision", "الرؤية الحاسوبية"),
    ("OBJECT_DETECTION", "Object detection", "اكتشاف الأجسام"),
    ("OBJECT_RECOGNITION", "Object recognition", "التعرف على الأجسام"),
    ("OBJECT_TRACKING", "Object tracking", "التتبع الآلي للأجسام"),
    ("AUTONOMOUS_NAVIGATION", "Autonomous navigation", "الملاحة الذاتية"),
    ("PATH_PLANNING", "Path planning", "تخطيط المسار"),
    ("OBSTACLE_AVOIDANCE", "Obstacle avoidance", "تجنب الاصطدام"),
    ("BEHAVIOUR_DETECTION", "Behaviour detection", "اكتشاف السلوك"),
    ("ANOMALY_DETECTION", "Anomaly detection", "اكتشاف الحالات الشاذة"),
    ("SENSOR_FUSION", "Sensor fusion", "دمج بيانات المستشعرات"),
    ("PREDICTIVE_MAINTENANCE", "Predictive maintenance", "الصيانة التنبؤية"),
    ("SWARM_COORDINATION", "Swarm coordination", "تنسيق الأسراب"),
    ("MISSION_PLANNING", "Autonomous mission planning", "التخطيط الذاتي للمهام"),
    ("DECISION_SUPPORT", "Decision support", "دعم القرار"),
)
# level, English, Arabic, description EN, description AR, minimum supported, required technology codes
AI_LEVELS = (
    (1, "AI assistance", "مساعدة الذكاء الاصطناعي", "At least one AI function assists the operator.",
     "وظيفة ذكاء اصطناعي واحدة على الأقل تساعد المشغل.", 1, ""),
    (2, "Partial autonomy", "استقلالية جزئية", "At least 3 functions including object detection.",
     "3 وظائف على الأقل تشمل اكتشاف الأجسام.", 3, "OBJECT_DETECTION"),
    (3, "Conditional autonomy", "استقلالية مشروطة", "At least 5 functions including autonomous navigation and obstacle avoidance.",
     "5 وظائف على الأقل تشمل الملاحة الذاتية وتجنب الاصطدام.", 5, "AUTONOMOUS_NAVIGATION,OBSTACLE_AVOIDANCE"),
    (4, "High autonomy", "استقلالية عالية", "At least 7 functions including path planning and sensor fusion.",
     "7 وظائف على الأقل تشمل تخطيط المسار ودمج بيانات المستشعرات.", 7, "PATH_PLANNING,SENSOR_FUSION"),
    (5, "Full autonomy", "استقلالية كاملة", "At least 10 functions including swarm coordination and decision support.",
     "10 وظائف على الأقل تشمل تنسيق الأسراب ودعم القرار.", 10, "SWARM_COORDINATION,DECISION_SUPPORT"),
)
