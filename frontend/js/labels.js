// Every interface string. English here; the Arabic twin of each key is in js/i18n/ar/index.js (same keys), loaded
// only when Arabic is chosen. A key missing in Arabic falls back to English. Names of records and list entries come
// from the server in both languages (nameEn / nameAr): pick with name().
import { language } from './lib/i18n.js';
import PROJECTS from './labels-projects.js';
import OPERATIONS from './labels-operations.js';
import ADMIN from './labels-admin.js';

const EN = {
  app: { name: 'Capability Portfolio Command', short: 'Capability management information system',
    subtitle: 'Capabilities and portfolio management', classification: 'Classification: to be set later' },
  common: {
    none: '—', all: 'All', save: 'Save', cancel: 'Cancel', close: 'Close', edit: 'Edit', add: 'Add', archive: 'Archive',
    restore: 'Restore', loading: 'Loading…', retry: 'Try again', search: 'Search', filters: 'Filters', clear: 'Clear filters',
    export: 'Export', exportCsv: 'CSV', print: 'Print', yes: 'Yes', no: 'No', records: '{n} records', page: 'Page {page} of {pages}',
    previous: 'Previous', next: 'Next', table: 'Table', cards: 'Cards', details: 'Details', history: 'History',
    reason: 'Reason for the change (optional)', saved: 'Saved.', archived: 'Archived', basis: 'Basis:', view: 'Open',
    savedViews: 'Saved views', saveView: 'Save current view', viewName: 'Name of the view', deleteView: 'Delete view',
    noResults: 'No records match these filters.', comingSoon: 'This module is part of a later build phase.',
    days: '{n} days', months: '{n} months', years: '{n} years', yesNo: { true: 'Yes', false: 'No' },
    sinceMonth: 'm', sinceQuarter: 'q', sinceYear: 'y', aed: 'AED', million: '{n} M AED', thousand: '{n} K AED',
    notSet: 'Not set', allDepartments: 'All departments', today: 'Today', unknown: 'Unknown',
  },
  nav: {
    home: 'Home', dashboard: 'Executive dashboard', analytics: 'Dashboard analytics', capabilities: 'Capabilities',
    allCapabilities: 'All capabilities', completion: 'Capability completion', gaps: 'Capability gap analysis',
    aiCapabilities: 'AI capabilities', development: 'Development potential', projects: 'Projects',
    allProjects: 'All projects', activeProjects: 'Active projects', delayedProjects: 'Delayed projects',
    timeline: 'Strategic timeline', gantt: 'Gantt chart', milestones: 'Milestones', risks: 'Risks', issues: 'Issues',
    testing: 'Testing and evaluation', maintenance: 'Maintenance and technical readiness', decision: 'Decision support',
    reports: 'Reports and analytics', documents: 'Documents', alerts: 'Alerts', settings: 'Settings', audit: 'Audit history',
    footer: 'Unmanned systems capability command. Classification: to be set later.',
  },
  top: {
    search: 'Search capabilities, assets, serial numbers, projects and contracts…', viewAs: 'View as',
    viewAsSelf: 'My role', previewing: 'Preview: you are seeing the system as «{role}». Changes are disabled.',
    leavePreview: 'Leave preview', signOut: 'Sign out', alerts: 'Alerts', menu: 'Menu', language: 'Language',
  },
  auth: {
    title: 'Sign in', username: 'Username', password: 'Password', submit: 'Sign in', failed: 'Invalid username or password.',
    directoryHint: 'Use your Windows username (for example U12345) and password.',
    mockHint: 'Demo: sign in as mock.admin, mock.exec, mock.head, mock.capability, mock.pm, mock.maint, mock.test, mock.analyst or mock.viewer. Password: Mock-Pass-123',
  },
  errors: { generic: 'Something went wrong. Try again.', network: 'The server cannot be reached. Check the connection.',
    notFound: 'That page or record was not found.', forbidden: 'Your role does not allow that.' },
  categories: { UAV: 'UAV', UGV: 'UGV', USV: 'USV', UUV: 'UUV' },
  priority: { CRITICAL: 'Critical', HIGH: 'High', MEDIUM: 'Medium', LOW: 'Low' },
  rag: { GREEN: 'Green', AMBER: 'Amber', RED: 'Red', GREY: 'Not rated' },
  fields: {
    code: 'ID', assetId: 'Asset ID', serial: 'Serial number', model: 'Model', category: 'Category', department: 'Department',
    site: 'Location', status: 'Status', readiness: 'Readiness', opReadiness: 'Operational readiness',
    techReadiness: 'Technical readiness', missionReadiness: 'Mission readiness', maintReadiness: 'Maintenance readiness',
    overallReadiness: 'Overall readiness', acquisitionDate: 'Acquisition date', deliveryDate: 'Expected delivery',
    acquisitionMethod: 'Acquisition method', contract: 'Contract', warranty: 'Warranty end', warrantyActive: 'Warranty',
    unitValue: 'Unit value', serviceLife: 'Service life', hours: 'Operating hours', responsible: 'Responsible officer / unit',
    notes: 'Notes', manufacturer: 'Manufacturer', supplier: 'Supplier', role: 'Role', unitCost: 'Unit cost',
    nameEn: 'Name (English)', nameAr: 'Name (Arabic)', required: 'Required', available: 'Available',
    operational: 'Operational', pipeline: 'Pipeline', underAcquisition: 'Under acquisition', underDevelopment: 'Under development',
    underTest: 'Under test', gap: 'Current gap', forecastGap: 'Forecast gap', priority: 'Priority',
    currentCompletion: 'Current completion', forecastCompletion: 'Forecast completion', linkedProjects: 'Linked projects',
    closureDate: 'Expected gap closure', notClosed: 'Not closed by current plan', age: 'Age', targetDate: 'Target date',
    requiredQty: 'Required quantity', models: 'Models', assets: 'Assets', requirement: 'Requirement', year: 'Acquisition year',
    readinessBand: 'Readiness band', updatedAt: 'Last updated', version: 'Version',
  },
  methods: { DIRECT_CONTRACT: 'Direct contract', TENDER: 'Tender', GOVERNMENT: 'Government-to-government',
    DONATION: 'Donation', DEVELOPMENT: 'In-house development', OTHER: 'Other' },
  bands: { HIGH: '80–100%', MEDIUM: '50–79%', LOW: 'Below 50%' },
  warrantyStates: { ACTIVE: 'Active', EXPIRED: 'Expired or none' },
  statusGroups: { AVAILABLE: 'Available', OPERATIONAL: 'Operational', PIPELINE: 'In the pipeline' },
  registry: {
    title: 'All capabilities', subtitle: 'Select any number to see its source records.', tabAssets: 'Assets',
    tabModels: 'Capability models', tabRequirements: 'Capability requirements', addAsset: 'Asset', addModel: 'Model',
    addRequirement: 'Requirement', categoryTitle: '{code} — {name}', assetsCount: '{n} assets',
  },
  asset: { tabs: { overview: 'Overview', acquisition: 'Acquisition', readiness: 'Readiness', history: 'Status history', tests: 'Tests', maintenance: 'Maintenance',
    projects: 'Projects', activity: 'Activity' }, newTitle: 'New asset', editTitle: 'Edit asset {code}' },
  model: { tabs: { assets: 'Assets', specs: 'Technical capabilities', ai: 'AI capability', projects: 'Projects', requirements: 'Requirements',
    activity: 'Activity' }, newTitle: 'New capability model', editTitle: 'Edit model {code}', specsEdit: 'Edit technical capabilities',
    sections: { PERFORMANCE: 'Performance', SENSORS: 'Sensors and payloads', COMMUNICATIONS: 'Communications, navigation and autonomy',
      ENVIRONMENT: 'Environment and operation', OTHER: 'Other' } },
  requirement: { newTitle: 'New capability requirement', editTitle: 'Edit requirement {code}' },
  completion: {
    title: 'Capability completion',
    subtitle: 'Forecast completion counts only projects in approved statuses (configurable in Settings > Business rules).',
    byDepartment: 'By department', byCategory: 'By category', total: 'Overall', current: 'Current completion',
    forecast: 'Forecast completion', requirements: 'Capability requirements', criticalGaps: 'Critical gaps',
    currentForecast: 'Current vs forecast completion',
  },
  gaps: { title: 'Capability gap analysis', subtitle: 'Required − available = gap. Forecast adds projects in approved statuses.',
    heatmap: 'Gap heatmap', current: 'Current gap', forecast: 'Forecast gap', byDepartment: 'Department comparison',
    byCategory: 'Category comparison', register: 'Gap register', critical: 'Critical gap', legendCritical: '! = critical' },
  dashboard: {
    title: 'Executive capability position', subtitle: 'As of {date} · {scope} · Select any number to see its source records.',
    inventory: 'Inventory', pipeline: 'In preparation', portfolio: 'Portfolio', attention: 'Items requiring leadership attention',
    matrix: 'Capability overview matrix', statusDistribution: 'Capability status distribution',
    completionByDept: 'Capability completion by department', currentVsForecast: 'Current vs forecast completion',
    gapHeatmap: 'Capability gap heatmap', sites: 'Capability locations', portfolioHealth: 'Project portfolio overview',
    timeline: 'Project completion timeline', summaryButton: 'Executive summary',
    kpi: { capabilities: 'Total capabilities', assets: 'Total assets', ready: 'Ready assets', maintenance: 'Under maintenance',
      notReady: 'Not ready', awaiting: 'Awaiting replacement', writtenOff: 'Written off', acquisition: 'Under acquisition',
      development: 'Under development', test: 'Under test', criticalGaps: 'Critical capability gaps',
      activeProjects: 'Current projects', devProjects: 'Projects in development', testProjects: 'Projects in testing',
      delayedProjects: 'Delayed projects', due30: 'Completing within 30 days', due90: 'Completing within 90 days' },
    trend: '{m} m · {q} q · {y} y', drillTitle: '{title}', drillCount: '{n} records', current: 'Current', pipelineCol: 'Pipeline',
    total: 'Total', readyAssets: 'Ready assets', notReadyAssets: 'Not ready / maintenance',
  },
  history: { CREATE: 'Created', UPDATE: 'Changed', ARCHIVE: 'Archived', RESTORE: 'Restored', by: 'by {name}',
    empty: 'No changes recorded yet.', field: '{field}: {from} → {to}' },
  dateField: { placeholder: 'dd/mm/yyyy', invalid: 'Enter the date as dd/mm/yyyy.', choose: 'Choose date',
    chooseFor: 'Choose date: {field}', previousMonth: 'Previous month', nextMonth: 'Next month' },
  confirm: { discardTitle: 'Discard unsaved changes?', discardBody: 'You have changes that have not been saved.',
    discard: 'Discard changes', keepEditing: 'Keep editing' },
  placeholder: { title: '{name}', body: 'This module is planned in the build plan and arrives in a later phase. The data model and permissions are ready for it.' },
};

Object.assign(EN, PROJECTS, OPERATIONS, ADMIN);

// Modules of later phases add their strings here (an English object and its Arabic twin).
export function extendLabels(en) { Object.assign(EN, en); }

let AR = null;

export async function loadLanguage() {
  if (language() === 'ar') {
    const parts = await Promise.all([import('./i18n/ar/index.js'), import('./i18n/ar/projects.js'), import('./i18n/ar/operations.js'), import('./i18n/ar/admin.js')]);
    AR = Object.assign({}, ...parts.map((m) => m.default));
  }
}

function lookup(dict, path) {
  let node = dict;
  for (const part of path.split('.')) {
    if (node == null || typeof node !== 'object') return undefined;
    node = node[part];
  }
  return node;
}

export function t(path, vars) {
  let text = (AR && lookup(AR, path)) ?? lookup(EN, path);
  if (text === undefined) return path;
  if (typeof text !== 'string') return text;
  if (vars) text = text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] === undefined ? `{${k}}` : String(vars[k])));
  return text;
}

// Pick the record's name in the interface language (falls back to the other language when one is missing).
export function name(entry, field = 'name') {
  if (!entry) return t('common.none');
  const en = entry[`${field}En`];
  const ar = entry[`${field}Ar`];
  return (language() === 'ar' ? (ar || en) : (en || ar)) ?? t('common.none');
}

// A name or code inside a sentence, isolated so a Latin code does not reorder Arabic text.
export function isolate(text) {
  return `⁨${text}⁩`;
}

export function plural(path, n) {
  return t(path, { n });
}

// The server writes messages in English; Arabic shows the Arabic one for known codes.
export function serverText(code, message) {
  if (language() === 'ar' && AR && AR.server) {
    return AR.server[code] || (message && AR.server.messages && AR.server.messages[message]) || message;
  }
  return message;
}
