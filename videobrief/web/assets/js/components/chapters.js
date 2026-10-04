import {el, section} from '../dom.js';
import {evidenceBlock} from './evidence.js';

export function renderChapters(data, onJump) {
  const container = section('chapters', '按需查证', '只有需要上下文、原文或精确时间时才展开。');
  const list = el('div', 'chapter-list');
  data.chapters.forEach((chapter, index) => {
    const item = el('details', 'chapter');
    item.dataset.search = [
      chapter.title, chapter.body, ...(chapter.points || []),
      ...(chapter.evidence || []).map(value => value.quote),
    ].join(' ').toLowerCase();
    const summary = el('summary');
    summary.append(
      el('span', 'chapter-index', `${String(index + 1).padStart(2, '0')} · ${chapter.time}`),
      el('span', 'chapter-title', chapter.title),
      el('span', 'chapter-arrow', '展开'),
    );
    const content = el('div', 'chapter-content');
    content.append(
      el('div', 'chapter-takeaway', chapter.points?.[0] || chapter.body),
      el('div', 'chapter-body', chapter.body),
    );
    const jumpButton = el('button', 'time-btn', '查看原片段');
    jumpButton.type = 'button';
    jumpButton.addEventListener('click', () => onJump?.(Number(chapter.start_seconds) || 0));
    content.append(jumpButton);
    if ((chapter.evidence || []).length) {
      content.append(evidenceBlock({
        evidence_ids: chapter.evidence.map(value => value.evidence_id).filter(Boolean),
        evidence: chapter.evidence,
      }, onJump, '核对字幕'));
    }
    item.append(summary, content);
    list.append(item);
  });
  container.append(list);
  return container;
}
