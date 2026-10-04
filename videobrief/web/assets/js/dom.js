export const $ = selector => document.querySelector(selector);

export function el(tag, className = '', text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

export function fmt(seconds) {
  const value = Number(seconds) || 0;
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const rest = Math.floor(value % 60);
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${minutes}:${String(rest).padStart(2, '0')}`;
}

export function section(id, title, lead = '') {
  const node = el('section', 'section');
  node.id = id;
  node.append(el('h2', 'section-title', title));
  if (lead) node.append(el('p', 'section-lead', lead));
  return node;
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}
