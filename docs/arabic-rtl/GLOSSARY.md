# Arabic glossary (interface terms)

The Arabic interface uses Modern Standard Arabic, written for the people who run and repair the fleet: short, formal, plain. One English term always gets the same Arabic word, so this list wins over a translator's own preference. Add a line here before using a new term in more than one place.

## Style rules

- **Voice:** use the formal imperative for buttons and actions, for example «احفظ» (Save) or «أرسل للاعتماد» (Submit for approval). Use a verbal noun where English uses a noun label, for example «تسجيل الدخول» (Sign in). Work in progress takes «جارٍ»: «جارٍ الحفظ…» (Saving…), «جارٍ التحميل…» (Loading…).
- **Digits:** keep Western digits (0-9) everywhere. The app formats numbers and dates with `ar-AE-u-ca-gregory-nu-latn`. Never type Arabic-Indic digits (٠-٩) into a label.
- **Dates (26 Oct 2026):** dd/mm/yyyy in both languages, `26/10/2026`, written left to right inside Arabic text (built in `lib/format.js` without the right-to-left marks of Arabic `Intl` numeric dates); with a time, `26/10/2026 02:05 م`. Spelled-out parts: يوم / شهر / سنة (the date box's placeholder and its error «أدخل التاريخ بصيغة يوم/شهر/سنة.»). Month names stay only in month headings («أكتوبر 2026») and the calendar's title.
- **Placeholders:** keep every `{name}` exactly as in English, spelled the same. Move it to wherever Arabic word order needs it. Never translate what is inside the braces.
- **Plurals:** where English has `{ one, other }`, Arabic gives all six forms: `zero`, `one`, `two`, `few` (3–10), `many` (11–99) and `other` (100+, also used for fractions). Every plural object must have `other`.
  - Example:
    ```js
    { zero: 'لا أعطال', one: 'عطل واحد', two: 'عطلان', few: '{n} أعطال', many: '{n} عطلًا', other: '{n} عطل' }
    ```
- **Counts inside plain strings:** for a count in a string that is not a plural object, write a form that reads correctly for any number. The usual way is to put the counted noun first, for example «الأعطال: {n}». Only use «{n} عطل» when no better form fits.
- **Arrows:** `→` in an English template becomes `←` in Arabic, because the text runs right to left. `›` in a path stays `›`; the browser mirrors it.
- **Punctuation:** use the Arabic comma `،`, the Arabic question mark `؟` and the Arabic semicolon `؛`. Keep the ellipsis `…`, the middle dot `·` and the dash `—` as they are.
- **Codes and names:** leave codes, references and product names in Latin script, for example `DEF-12`, `IMO`, `PDF` or `Excel`.
- **Units:**
  - km → كم
  - KB → ك.ب
  - MB → م.ب
  - Percent: the number formatter adds the sign.

## Terms

| English | Arabic | Notes |
|---|---|---|
| Capability Portfolio Command | لوحة أعطال الأسطول | app name |
| fleet | الأسطول | |
| station | المحطة / المحطات | |
| class (vessel class), ship type | الفئة / الفئات، نوع السفينة | "Class" = فئة السفن |
| ship | السفينة / السفن | |
| fleet number | رقم الأسطول | |
| IMO number | رقم IMO | |
| defect | العطل / الأعطال | |
| issue type | نوع المشكلة / أنواع المشكلات | |
| severity | الخطورة | |
| Critical / High / Medium / Low | حرج / عالية / متوسطة / منخفضة | severity names (short labels may use حرجة for agreement with خطورة) |
| status | الحالة | |
| Open | مفتوح | |
| In progress | قيد التنفيذ | |
| Awaiting approval | بانتظار الاعتماد | `PENDING_APPROVAL` |
| Resolved | تم الإصلاح | |
| Closed | مغلق | |
| Submit for approval | أرسل للاعتماد | button |
| Approve | اعتمد | button; noun «الاعتماد» |
| Send back | أعِد للعمل | button; "sent back" = أُعيد للعمل |
| repair notes | ملاحظات الإصلاح | |
| verification notes | ملاحظات التحقق | |
| reason | السبب | |
| approver | المعتمِد | |
| reported / recorded | سُجِّل | "recorded by" = سجّله |
| submitted by (who recorded a defect) | سجّله | the "Submitted by" column and fact |
| submitted by (a repair, for approval) | أرسله | My work, notifications |
| Resolve (button) / resolve dialog | أكّد الإصلاح / تأكيد الإصلاح | approvers only |
| target date, approximate solving date | التاريخ المتوقع للإصلاح | |
| At sea (ship location) | في البحر | the first location suggestion on the submit form; stored as typed |
| overdue | متأخر | |
| due soon / due today | يستحق قريبًا / يستحق اليوم | |
| outstanding (not done) | غير منجز / قائم | "defects not done" = أعطال غير منجزة |
| readiness | الجاهزية | |
| Fit for sea | صالحة للإبحار | GREEN |
| Sail with caution | الإبحار بحذر | YELLOW |
| Restricted technically — check before sailing | مقيدة فنيًا — تحقّق قبل الإبحار | ORANGE |
| Not fit for sea technically | غير صالحة للإبحار فنيًا | RED |
| system (ship system) | النظام | |
| Hull / Propulsion / Electrical / Navigation / Safety / Other | البدن / الدفع / الكهرباء / الملاحة / السلامة / أخرى | the six built-in systems. A system an admin adds (since 26 Oct 2026) carries its own Arabic name, typed by the admin (required); the app shows that name as it was typed |
| Systems (Issue types dialog) / built-in system / added system | الأنظمة / مضمّن / مُضاف | Issue types page, Edit mode |
| Rename (button) / rename (dialog title) | أعِد التسمية / إعادة تسمية | |
| attachment | المرفق / المرفقات | |
| archive (verb) / archived | أرشِف / مؤرشف | the Archived badge on a station, class or ship reads «مؤرشفة» (agrees with محطة / فئة / سفينة) |
| restore | استعِد | |
| audit history | سجل التدقيق | |
| Audit (header link) | التدقيق | short form in the header, which has no room for سجل التدقيق |
| notifications | الإشعارات | |
| My work | مهامي | |
| Submit defects (page) | تسجيل الأعطال | |
| Operations (page) | العمليات | |
| Summary (page) | الملخص | |
| Stations (page) | المحطات | |
| Issue types (page) | أنواع المشكلات | |
| Users (page) | المستخدمون | |
| Archived (page) | الأرشيف | |
| Edit mode | وضع التعديل | |
| Refresh | تحديث | |
| Sign in / Sign out | تسجيل الدخول / تسجيل الخروج | |
| username / password | اسم المستخدم / كلمة المرور | |
| company directory (LDAP / Active Directory) | دليل الشركة | directory sign-in, AUTH_MODE=ldap |
| Windows account / Windows username | حساب Windows / اسم المستخدم في Windows | "Windows" stays in Latin letters |
| Look up (in the directory) | بحث | Users & access, directory mode |
| CEO | الرئيس التنفيذي | role |
| Admin | مسؤول النظام | role |
| Top submitter | مُبلِّغ رئيسي | role (records on every station, approves repairs) |
| Station submitter | مُبلِّغ محطة | role |
| demo data | بيانات تجريبية | |
| Save / Cancel / Close / Delete / Edit / Add | احفظ / إلغاء / إغلاق / حذف / تعديل / إضافة | |
| Print | طباعة | |
| Download Excel | تنزيل ملف Excel | |
| required / optional | مطلوب / اختياري | |
| search | بحث | |
