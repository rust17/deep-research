todo:
    - subagent
    - 流式输出 async/await
    - [x] 用小模型总结，大模型指挥
    - [x] 支持 pdf 文件阅读
    - [ ] 动态检测用户语言，指示大模型用用户语言回答
    - [x] 改成根据 token 数已逼近模型最大上下文来压缩上下文
    - [x] 统一日志和 history 每个单元的结构
problem:
    - 架构不够清晰
    - [x] web_search 工具不够强大
    - [x] 最后的报告过于简陋
    - [x] gui 调用工具一直"正在调用中"
    - [x] gui 开始调研之后按钮要禁止按了
    - [x] web_search 工具依然存在超时等问题

---

refactor:
    - [x] tool_call 重构：分成两个 tool，search（返回摘要） 和 visit（原来集成在 web_search 里的功能），让大模型按需访问，不再全部访问
    - [x] visit 工具的流程是现在的 crawl + summary
    - [x] tool_call 返回内容也要放进 message_history，tool_call 要遵循固定的返回格式 {"type": "text", "text": content}
    - [x] 流程变更：改成在循环里，不断积累 message_history，大模型的输出要放进 message_history 里，大模型 message_history 的格式为：{"role": "assistant|user", "content": ""}，让大模型根据 message_history 推理，决定 tool_call 还是 break
    - [x] 把所有消息放进 message_history，不再保存到临时文件了，message_history 即是所有的上下文

---
refactor:
    - [ ] 整合 message_history 和 _emit