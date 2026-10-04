import {el, fmt} from '../dom.js';
import {evidenceBlock} from './evidence.js';

export function renderDecisionHero(data, onJump) {
  const decision = data.decision_brief;
  const hero = el('section', 'hero decision');
  hero.id = 'overview';

  const labels = el('div', 'hero-labels');
  labels.append(
    el('span', 'pill', data.fingerprint?.type_label || '视频内容'),
    el('span', 'pill neutral', `${data.fingerprint?.information_density || '未知'}信息密度`),
    el('span', 'pill neutral', `原视频 ${fmt(data.metrics?.duration_seconds)}`),
  );
  hero.append(
    labels,
    el('h1', '', data.title || '未命名知识页'),
    el('div', 'decision-kicker', decision.question),
    el('div', 'decision-answer', decision.answer),
  );

  if (decision.takeaways.length) {
    const heading = el('div', 'decision-points-title', '真正重要的');
    const points = el('div', 'decision-points');
    decision.takeaways.forEach((item, index) => {
      const card = el('article', 'decision-point');
      card.append(el('div', 'num', index + 1));
      const body = el('div');
      body.append(el('h3', '', item.title || '关键结论'), el('p', '', item.detail || ''));
      if ((item.evidence || []).length) body.append(evidenceBlock(item, onJump));
      const at = el('button', 'time-btn', item.time || '00:00');
      at.type = 'button';
      at.addEventListener('click', () => onJump?.(Number(item.seconds) || 0));
      card.append(body, at);
      points.append(card);
    });
    hero.append(heading, points);
  }

  const grid = el('div', 'decision-grid');
  const watch = el('div', 'decision-cell watch');
  watch.append(
    el('span', '', '观看建议'),
    el('b', '', decision.watch_verdict || '直接阅读即可'),
    el('small', '', decision.watch_reason || ''),
  );
  const context = el('div', 'decision-cell');
  if (decision.boundary) {
    context.append(el('span', '', '内容边界'), el('b', '', decision.boundary));
  } else if (decision.why_it_matters) {
    context.append(el('span', '', '为什么重要'), el('b', '', decision.why_it_matters));
  } else {
    context.append(el('span', '', '理解方式'), el('b', '', '先掌握结论，需要执行或核验时再展开原始内容。'));
  }
  grid.append(watch, context);
  hero.append(grid);

  if (decision.why_it_matters && decision.boundary) {
    const why = el('div', 'decision-context');
    why.append(el('b', '', '为什么重要'), document.createTextNode(decision.why_it_matters));
    hero.append(why);
  }

  const duration = Number(data.metrics?.duration_seconds) || 0;
  const read = (Number(data.metrics?.estimated_read_minutes) || 1) * 60;
  const watchSeconds = Number(decision.watch_seconds) || 0;
  const saved = Math.max(0, duration - read - watchSeconds);
  const metrics = el('div', 'metrics');
  for (const [value, label, className] of [
    [fmt(read), '预计阅读', ''], [fmt(watchSeconds), '需看原片', 'watch'],
    [fmt(saved), '预计节省', 'saved'], [data.metrics?.evidence_count || 0, '可核对证据', ''],
  ]) {
    const metric = el('div', `metric ${className}`.trim());
    metric.append(el('b', '', value), el('span', '', label));
    metrics.append(metric);
  }
  hero.append(metrics);

  const agentText = data.agent?.mode === 'smart'
    ? `DeepSeek 已完成分析与证据审计；保留 ${data.agent.validated_insights || 0} 条高价值观点，审计可信度 ${data.agent.audit_confidence || '—'}。${data.agent.structure_fallback ? '类型结构不足，已保留完整本地结构。' : ''}`
    : '当前使用本地规则引擎；选择智能分析后会进一步综合结论并执行证据审计。';
  hero.append(el('div', 'engine', agentText));
  return hero;
}
