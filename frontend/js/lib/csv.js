// CSV export of the defects a submitter is looking at. Cells that could be read as spreadsheet formulas
// (leading = + - @ or control characters) are prefixed with an apostrophe so they stay plain text.

function cell(value) {
  let text = value === null || value === undefined ? '' : String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(header, rows) {
  // ﻿ lets Excel open UTF-8 (Arabic vessel or place names) correctly.
  return `﻿${[header, ...rows].map((row) => row.map(cell).join(',')).join('\r\n')}\r\n`;
}

export function downloadCsv(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
