function decisionFallback(data) {
  const watchSeconds = (data.must_watch_segments || []).reduce(
    (sum, item) => sum + Math.max(0, Number(item.end_seconds) - Number(item.start_seconds)), 0,
  );
  return {
    question: data.quick_brief?.central_question || data.title || '这个视频讲了什么？',
    answer: data.quick_brief?.direct_answer || data.summary || '',
    takeaways: (data.key_insights || []).slice(0, 3),
    watch_verdict: watchSeconds ? '只需回看关键片段' : '直接阅读即可',
    watch_reason: watchSeconds ? '大部分内容可以直接阅读。' : '没有检测到必须依赖画面的内容。',
    watch_seconds: watchSeconds,
    why_it_matters: data.quick_brief?.why_it_matters || '',
    boundary: data.quick_brief?.limitation || '',
  };
}

export function decodeBrief(payload) {
  if (!payload || typeof payload !== 'object') throw new Error('知识页数据格式不正确');
  const brief = {...payload};
  for (const field of ['chapters', 'evidence_store', 'key_insights', 'must_watch_segments', 'content_map']) {
    brief[field] = Array.isArray(brief[field]) ? brief[field] : [];
  }
  brief.metrics = brief.metrics && typeof brief.metrics === 'object' ? brief.metrics : {};
  brief.fingerprint = brief.fingerprint && typeof brief.fingerprint === 'object' ? brief.fingerprint : {};
  brief.agent = brief.agent && typeof brief.agent === 'object' ? brief.agent : {mode: 'fast'};
  brief.content_model = brief.content_model && typeof brief.content_model === 'object'
    ? {...brief.content_model, items: Array.isArray(brief.content_model.items) ? brief.content_model.items : []}
    : {template: brief.content_type || 'lecture', items: []};
  const decision = brief.decision_brief && typeof brief.decision_brief === 'object'
    ? brief.decision_brief : decisionFallback(brief);
  brief.decision_brief = {
    ...decision,
    question: decision.question || brief.title || '',
    answer: decision.answer || brief.summary || '',
    takeaways: Array.isArray(decision.takeaways) ? decision.takeaways.slice(0, 3) : [],
    watch_seconds: Number(decision.watch_seconds) || 0,
  };
  return brief;
}

export function decodeJob(payload) {
  if (!payload || typeof payload !== 'object' || !payload.id) throw new Error('任务数据格式不正确');
  return {
    ...payload,
    progress: Math.max(0, Math.min(100, Number(payload.progress) || 0)),
    message: String(payload.message || ''),
    result: payload.result ? decodeBrief(payload.result) : null,
  };
}
