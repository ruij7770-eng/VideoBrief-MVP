import {el} from '../dom.js';

export function evidenceBlock(item, onJump, label = '核对证据') {
  const proof = el('details', 'evidence');
  const ids = Array.isArray(item.evidence_ids) ? item.evidence_ids : [];
  proof.append(el('summary', '', `${label}${ids.length ? ` · ${ids.join('、')}` : ''}`));
  for (const value of item.evidence || []) {
    const row = el('div', 'quote');
    const at = el('button', 'time-btn', `[${value.time || '00:00'}]`);
    at.type = 'button';
    at.addEventListener('click', () => onJump?.(Number(value.seconds) || 0));
    row.append(at, document.createTextNode(` ${value.quote || ''}`));
    proof.append(row);
  }
  return proof;
}
