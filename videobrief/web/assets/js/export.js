import {escapeHtml, fmt} from './dom.js';
import {modelViews} from './components/structure.js';

export function exportBrief(data) {
  if (!data) return;
  const decision = data.decision_brief;
  const takeaways = decision.takeaways.map(item => (
    `<li><b>${escapeHtml(item.title)}</b><br>${escapeHtml(item.detail)}</li>`
  )).join('');
  const typed = data.content_model.items.map(item => (
    `<details><summary><b>${escapeHtml(modelViews[data.content_model.template]?.roles[item.role] || item.role)} · ${escapeHtml(item.title)}</b></summary>` +
    `<p>${escapeHtml(item.detail)}</p>` +
    (item.evidence || []).map(value => `<blockquote><b>${escapeHtml(value.evidence_id)} · ${escapeHtml(value.time)}</b><br>${escapeHtml(value.quote)}</blockquote>`).join('') +
    `</details>`
  )).join('');
  const chapters = data.chapters.map(chapter => (
    `<details><summary><b>${escapeHtml(chapter.time)} · ${escapeHtml(chapter.title)}</b></summary><p>${escapeHtml(chapter.body)}</p></details>`
  )).join('');
  const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${escapeHtml(data.title)}</title><style>body{max-width:820px;margin:40px auto;padding:0 20px;font:16px/1.75 sans-serif;color:#151917}header{padding:30px;background:#e9f9f1;border-radius:18px}section{padding:25px 0;border-bottom:1px solid #ddd}details{padding:12px 0;border-bottom:1px solid #ddd}blockquote{background:#f5f7f5;border-left:3px solid #16c784;padding:10px 14px}</style><header><small>${escapeHtml(data.fingerprint.type_label)} · 原视频 ${fmt(data.metrics.duration_seconds)}</small><h1>${escapeHtml(data.title)}</h1><h2>${escapeHtml(decision.answer)}</h2><h3>真正重要的</h3><ol>${takeaways}</ol><p><b>观看建议：</b>${escapeHtml(decision.watch_verdict)}。${escapeHtml(decision.watch_reason)}</p></header><section><h2>${escapeHtml(modelViews[data.content_model.template]?.title || '完整理解')}</h2>${typed}</section><section><h2>按需查证</h2>${chapters}</section></html>`;
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([html], {type: 'text/html;charset=utf-8'}));
  link.download = `${String(data.title || 'videobrief').replace(/[\\/:*?"<>|]/g, '-')}.html`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
