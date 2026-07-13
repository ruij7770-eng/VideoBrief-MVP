import sys; sys.path.insert(0, '.')
from videobrief_service import parse_timestamped_transcript, make_brief
demo='''[00:00] 今天用实际案例讲怎么在 20 分钟内搭一个个人知识库。目标不是收集更多信息，而是让信息在需要时能被找到和使用。
[01:12] 第一部分是建立收集入口。灵感、网页和会议笔记都先放进 Inbox，不要在收集时分类。收集和整理是两件不同的事。
[03:28] 接下来定义最少的数据库字段：标题、来源、状态和主题。字段太多会降低录入意愿，先让系统容易用。
[06:40] 第二部分是处理流程。每天花十分钟清空 Inbox：删掉没用的、把可执行的转成任务、把值得保留的写成自己的理解。
[10:15] 模板能降低开始的阻力。阅读笔记模板只保留三个问题：核心观点是什么？它和我已知的什么有关？下一步我会怎么用？
[14:30] 最后是回顾。每周浏览项目和笔记，检查没推进的任务。知识库不是仓库，它应该持续帮你做决定。
[18:05] 总结：先建立单一入口，用最少字段降低摩擦，用固定回顾让信息进入行动。'''
rows = parse_timestamped_transcript(demo)
result = make_brief(rows)
print('标题:', result['title'])
print('结论:', result['summary'])
print('章节数:', len(result['chapters']))
for c in result['chapters']:
    print(f'  [{c["time"]}] {c["title"]}')
