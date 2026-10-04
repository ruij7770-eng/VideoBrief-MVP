import {decodeBrief, decodeJob} from './decoder.js';

export async function request(url, options) {
  const response = await fetch(url, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('服务器返回了无法解析的响应');
  }
  if (!response.ok) {
    const message = data?.error?.message || data?.detail || (typeof data?.error === 'string' ? data.error : '') || '请求失败';
    const error = new Error(message);
    error.code = data?.error?.code || 'REQUEST_FAILED';
    throw error;
  }
  return data;
}

export async function createTextJob(input) {
  return decodeJob(await request('/api/jobs', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(input),
  }));
}

export async function createUploadJob(file, model, mode, language) {
  const body = new FormData();
  body.append('media', file);
  if (language) body.append('language', language);
  return decodeJob(await request(`/api/jobs/upload?model_size=${encodeURIComponent(model)}&analysis_mode=${encodeURIComponent(mode)}&language=${encodeURIComponent(language || 'zh')}`, {
    method: 'POST', body,
  }));
}

export async function pollJob(id, onProgress) {
  for (;;) {
    await new Promise(resolve => setTimeout(resolve, 700));
    const job = decodeJob(await request(`/api/jobs/${encodeURIComponent(id)}`));
    onProgress?.(job);
    if (job.status === 'completed') return job.result;
    if (job.status === 'failed') throw new Error(job.error_info?.message || job.error || '处理失败');
  }
}

export async function listHistory() {
  const rows = await request('/api/history');
  return Array.isArray(rows) ? rows : [];
}

export async function getBrief(id) {
  return decodeBrief(await request(`/api/history/${encodeURIComponent(id)}`));
}

export async function askBrief(id, question) {
  return request(`/api/briefs/${encodeURIComponent(id)}/ask`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question}),
  });
}

export function getAgentStatus() {
  return request('/api/agent/status');
}
