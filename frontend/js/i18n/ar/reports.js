// Arabic twin of js/labels-reports.js.
export default {
  reports: {
    title: 'التقارير والتحليلات', subtitle: '{n} تقريراً معرفاً مسبقاً مستخرجة مباشرة من بيانات النظام ضمن صلاحياتك.',
    tabs: { catalogue: 'فهرس التقارير', builder: 'منشئ التقارير', schedules: 'التقارير المجدولة', history: 'سجل التقارير' },
    lang: { EN: 'الإنجليزية', AR: 'العربية', BILINGUAL: 'ثنائي اللغة' },
    export: { PDF: 'PDF', XLSX: 'Excel', CSV: 'CSV', PPTX: 'PowerPoint', PRINT: 'PDF جاهز للطباعة' },
    choose: 'اختر تقريراً من الفهرس.', searchReports: 'البحث في التقارير',
    header: { generated: 'تاريخ الإنشاء', by: 'أنشئ بواسطة', role: 'الدور', asOf: 'بتاريخ', language: 'اللغة', filters: 'عوامل التصفية المطبقة',
      none: 'لا يوجد (جميع السجلات ضمن صلاحياتك)', version: 'الإصدار' },
    records: 'السجلات',
    builder: { dataset: 'مجموعة البيانات', columns: 'الحقول', group: 'التجميع حسب', none: 'دون تجميع', filter: 'عامل التصفية', value: 'القيمة',
      sort: 'الترتيب حسب', visual: 'طريقة العرض', table: 'جدول', bar: 'رسم بياني شريطي', run: 'تشغيل التقرير', save: 'حفظ القالب',
      templates: 'القوالب المحفوظة', templateName: 'اسم القالب', shared: 'مشاركة مع المستخدمين الآخرين' },
    schedules: { add: 'جدولة', newTitle: 'تقرير مجدول جديد', name: 'الاسم', report: 'التقرير', frequency: 'التكرار',
      language: 'اللغة', format: 'الصيغة', time: 'وقت التشغيل', folder: 'مجلد الحفظ', next: 'التشغيل القادم',
      active: 'مفعّل', freq: { DAILY: 'يومي', WEEKLY: 'أسبوعي', MONTHLY: 'شهري', QUARTERLY: 'ربع سنوي' },
      note: 'يُنشئ الخادم التقارير المجدولة يومياً (run-schedules) في مجلد التقارير (REPORTS_OUTPUT_DIR، محلياً أو في مجلد مشترك على الشبكة) ضمن مجلد الحفظ لكل جدولة، ويمكن تنزيلها من سجل التقارير.' },
    history: { when: 'التاريخ', report: 'التقرير', by: 'بواسطة', language: 'اللغة', format: 'الصيغة', rows: 'السجلات', scheduled: 'مجدول', file: 'الملف', download: 'تنزيل' },
  },
};
