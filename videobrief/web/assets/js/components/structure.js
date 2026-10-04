import {el, fmt, section} from '../dom.js';
import {evidenceBlock} from './evidence.js';

export const modelViews = {
  tutorial: {title: '完整操作路线', lead: '需要执行时再展开；第一屏已经保留最重要的结论。', roles: {goal: '目标', prerequisite: '前置条件', step: '操作步骤', parameter: '参数与设置', pitfall: '容易出错', result: '完成结果'}},
  interview: {title: '完整观点结构', lead: '按人物立场、论据、分歧和未决问题展开。', roles: {topic: '核心议题', speaker_position: '人物立场', argument: '主要论据', disagreement: '观点分歧', key_quote: '关键原话', open_question: '未决问题'}},
  review: {title: '完整评测结构', lead: '按标准、优缺点、取舍和最终判断展开。', roles: {subject: '评测对象', criterion: '比较标准', pro: '优点', con: '缺点', tradeoff: '取舍', verdict: '最终判断'}},
  lecture: {title: '完整概念结构', lead: '按概念、关系、案例、结论和边界展开。', roles: {central_question: '核心问题', concept: '关键概念', relationship: '概念关系', example: '案例', conclusion: '结论', boundary: '适用边界'}},
  commentary: {title: '完整论证结构', lead: '区分事实、观点、推断、争议和不确定性。', roles: {topic: '讨论主题', fact: '事实', opinion: '作者观点', inference: '推断', controversy: '争议', uncertainty: '不确定性'}},
};

export function renderContentModel(data, onJump) {
  const model = data.content_model;
  const view = modelViews[model?.template];
  if (!view || !model.items.length) return null;
  const container = section('type-model', view.title, view.lead);
  const list = el('div', 'type-model');
  for (const item of model.items) {
    const row = el('details', 'type-item');
    const summary = el('summary');
    summary.append(
      el('span', 'type-role', view.roles[item.role] || item.role),
      el('span', 'type-title', item.title),
      el('span', 'type-time', item.time || '00:00'),
    );
    row.append(summary, el('p', 'type-detail', item.detail));
    if ((item.evidence || []).length) {
      const proof = evidenceBlock(item, onJump);
      proof.classList.add('type-proof');
      row.append(proof);
    }
    list.append(row);
  }
  container.append(list);
  return container;
}

export function renderWatch(data, onJump) {
  if (!data.must_watch_segments.length) return null;
  const container = section('watch', '需要回看的片段', '其余内容可以用阅读替代。');
  const list = el('div', 'watch-list');
  for (const item of data.must_watch_segments) {
    const card = el('article', 'watch-card');
    const text = el('div');
    text.append(
      el('b', '', `${item.time}—${fmt(item.end_seconds)} · ${item.preview}`),
      el('span', '', item.reason),
    );
    const button = el('button', 'btn', '查看片段');
    button.type = 'button';
    button.addEventListener('click', () => onJump?.(Number(item.start_seconds) || 0));
    card.append(text, button);
    list.append(card);
  }
  container.append(list);
  return container;
}
