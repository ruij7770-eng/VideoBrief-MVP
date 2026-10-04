import {
  askBrief, createTextJob, createUploadJob, getAgentStatus, getBrief, listHistory, pollJob,
} from './api.js';
import {createStore} from './state.js';
import {$, el, fmt} from './dom.js';
import {renderDecisionHero} from './components/decision.js';
import {renderContentModel, renderWatch} from './components/structure.js';
import {renderChapters} from './components/chapters.js';
import {exportBrief} from './export.js';

const demo = `[00:00] 今天演示如何在二十分钟内搭建个人知识库，解决信息散落和收藏后不再使用的问题。
[01:12] 第一步建立唯一的收集入口。灵感、网页和会议笔记都先放进收件箱。
[03:28] 现在看屏幕演示，点击新建数据库，只保留标题、来源、状态和主题四个字段。字段太多会增加录入阻力。
[06:40] 第二部分是处理流程。每天花十分钟清空收件箱，把信息放进项目或资料库。
[10:15] 阅读笔记模板只保留三个问题，复杂模板会降低记录意愿。
[14:30] 最后是回顾。每周检查没有推进的任务，让信息真正进入行动。
[18:05] 总结：先建立单一入口，用最少字段降低摩擦，再用固定回顾维持系统。`;

const store = createStore();

function setStatus(show, percent, text) {
  $('#status').classList.toggle('show', show);
  $('#progress').style.width = `${percent}%`;
  $('#percent').textContent = `${percent}%`;
  $('#statusText').textContent = text;
}

function jump(seconds) {
  const sourceUrl = store.getState().sourceUrl;
  if (!sourceUrl) {
    alert(`请在原视频 ${fmt(seconds)} 查看对应片段。`);
    return;
  }
  try {
    const url = new URL(sourceUrl);
    const isYouTube = ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'].includes(url.hostname);
    url.searchParams.set('t', isYouTube ? `${seconds}s` : seconds);
    window.open(url.toString(), '_blank', 'noopener');
  } catch {
    alert('原视频链接无效，暂时无法跳转。');
  }
}

function renderNav(data) {
  const nav = $('#nav');
  nav.replaceChildren();
  const items = [['overview', '核心结论']];
  if (data.content_model.items.length) items.push(['type-model', '完整理解']);
  if (data.must_watch_segments.length) items.push(['watch', '必看片段']);
  items.push(['chapters', '按需查证']);
  for (const [id, title] of items) {
    const button = el('button', '', title);
    button.type = 'button';
    button.addEventListener('click', () => document.getElementById(id)?.scrollIntoView({behavior: 'smooth'}));
    nav.append(button);
  }
}

function mountBrief(data) {
  $('#empty').style.display = 'none';
  $('#shell').classList.add('show');
  $('#create').classList.add('compact');
  $('#exportBtn').disabled = false;
  const blocks = [
    renderDecisionHero(data, jump),
    renderContentModel(data, jump),
    renderWatch(data, jump),
    renderChapters(data, jump),
  ].filter(Boolean);
  $('#main').replaceChildren(...blocks);
  renderNav(data);
  window.scrollTo({top: 0, behavior: 'smooth'});
}

store.subscribe((state, previous) => {
  if (state.brief && state.brief !== previous.brief) mountBrief(state.brief);
});

$('#form').addEventListener('submit', async event => {
  event.preventDefault();
  const file = $('#file').files[0];
  const url = $('#url').value.trim();
  const transcript = $('#transcript').value.trim();
  const analysisMode = $('#analysis').value;
    const language = $('#language').value;
  if (!file && !url && !transcript) {
    setStatus(true, 0, '请提供链接、字幕或本地文件');
    return;
  }
  $('#submit').disabled = true;
  try {
    setStatus(true, 5, '正在创建任务');
    store.dispatch({type: 'SOURCE_SELECTED', url: file ? '' : url});
    const job = file
      ? await createUploadJob(file, $('#model').value, analysisMode, language)
      : await createTextJob({url, transcript, analysis_mode: analysisMode, language});
    store.dispatch({type: 'JOB_UPDATED', job});
    const brief = await pollJob(job.id, value => {
      store.dispatch({type: 'JOB_UPDATED', job: value});
      setStatus(true, value.progress, value.message);
    });
    store.dispatch({type: 'BRIEF_LOADED', brief});
    await loadHistory();
  } catch (error) {
    store.dispatch({type: 'FAILED', error});
    setStatus(true, 0, `处理失败：${error.message}`);
  } finally {
    $('#submit').disabled = false;
  }
});

$('#demo').addEventListener('click', () => {
  $('#url').value = '';
  $('#file').value = '';
  $('#transcript').value = demo;
  $('#form').requestSubmit();
});

$('#newBtn').addEventListener('click', () => {
  $('#create').classList.remove('compact');
  $('#url').focus();
  window.scrollTo({top: 0, behavior: 'smooth'});
});

$('#search').addEventListener('input', event => {
  const query = event.target.value.trim().toLowerCase();
  let count = 0;
  document.querySelectorAll('.chapter').forEach(item => {
    const hit = !query || item.dataset.search.includes(query);
    item.classList.toggle('hidden', !hit);
    if (hit && query) {
      item.open = true;
      count += 1;
    }
  });
  $('#searchCount').textContent = query ? `找到 ${count} 个相关章节` : '';
});

$('#askForm').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('#question').value.trim();
  const brief = store.getState().brief;
  if (!question || !brief?.brief_id) return;
  const box = $('#askAnswer');
  box.classList.add('show');
  box.replaceChildren(el('p', '', '正在视频内容中查找证据……'));
  try {
    const answer = await askBrief(brief.brief_id, question);
    box.replaceChildren(el('p', '', answer.answer));
    if (answer.found) {
      const at = el('button', 'time-btn', `${answer.time} · 查看原片段`);
      at.type = 'button';
      at.addEventListener('click', () => jump(answer.seconds));
      box.append(at);
      for (const value of (answer.evidence || []).slice(0, 2)) {
        box.append(el('blockquote', '', `[${value.evidence_id || '证据'} · ${value.time}] ${value.quote}`));
      }
    }
  } catch (error) {
    box.replaceChildren(el('p', '', `提问失败：${error.message}`));
  }
});

async function loadHistory() {
  const list = $('#historyList');
  try {
    const rows = await listHistory();
    list.replaceChildren();
    for (const row of rows.slice(0, 10)) {
      const button = el('button');
      button.append(el('span', '', row.title), el('time', '', new Date(row.created_at).toLocaleString('zh-CN')));
      button.addEventListener('click', async () => {
        try {
          store.dispatch({type: 'SOURCE_SELECTED', url: row.url || ''});
          store.dispatch({type: 'BRIEF_LOADED', brief: await getBrief(row.id)});
        } catch (error) {
          setStatus(true, 0, `加载历史失败：${error.message}`);
        }
      });
      list.append(button);
    }
    if (!rows.length) list.append(el('p', 'section-lead', '还没有历史记录'));
  } catch {
    list.replaceChildren(el('p', 'section-lead', '历史记录暂时不可用'));
  }
}

$('#exportBtn').addEventListener('click', () => exportBrief(store.getState().brief));

async function loadAgentState() {
  const badge = $('#agentState');
  const smart = [...$('#analysis').options].find(option => option.value === 'smart');
  try {
    const status = await getAgentStatus();
    if (status.configured) {
      badge.textContent = `${status.provider} · ${status.model} 已连接`;
      badge.classList.remove('off');
      smart.disabled = false;
    } else {
      badge.textContent = 'DeepSeek 尚未配置';
      badge.classList.add('off');
      smart.disabled = true;
      smart.title = '请先配置 VIDEOBRIEF_LLM_API_KEY';
    }
  } catch {
    badge.textContent = '智能分析状态不可用';
    badge.classList.add('off');
    smart.disabled = true;
  }
}

loadAgentState();
loadHistory();
if (new URLSearchParams(location.search).get('demo') === 'fast') {
  $('#analysis').value = 'fast';
  setTimeout(() => $('#demo').click(), 0);
}
