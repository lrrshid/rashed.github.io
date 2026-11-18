// Readable names of database fields in the history (audit) views.
import { t } from '../labels.js';

const MAP = {
  serial_number: 'fields.serial', model_id: 'fields.model', department_id: 'fields.department', site_id: 'fields.site', unit_id: 'testing.fields.unit',
  parent_id: 'settings.unitParent',
  status_code: 'fields.status', readiness_operational: 'fields.opReadiness', readiness_technical: 'fields.techReadiness',
  readiness_mission: 'fields.missionReadiness', readiness_maintenance: 'fields.maintReadiness',
  acquisition_date: 'fields.acquisitionDate', expected_delivery_date: 'fields.deliveryDate',
  acquisition_method: 'fields.acquisitionMethod', contract_id: 'fields.contract', warranty_end_date: 'fields.warranty',
  unit_value: 'fields.unitValue', service_life_years: 'fields.serviceLife', operating_hours: 'fields.hours',
  responsible_en: 'fields.responsible', responsible_ar: 'fields.responsible', notes: 'fields.notes',
  name_en: 'fields.nameEn', name_ar: 'fields.nameAr', category_id: 'fields.category', manufacturer_id: 'fields.manufacturer',
  role_en: 'fields.role', role_ar: 'fields.role', unit_cost: 'fields.unitCost', required_qty: 'fields.requiredQty',
  priority: 'fields.priority', target_date: 'fields.targetDate', model_ids_text: 'fields.models', code: 'fields.code',
};

export function fieldLabel(field) {
  return MAP[field] ? t(MAP[field]) : field.replace(/_/g, ' ');
}
