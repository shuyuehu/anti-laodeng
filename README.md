# anti-laodeng

一个接入飞书的“反老登”私聊机器人原型，目标不是骂人，而是把职场里常见的爹味、经验压人、模糊施压、关系绑架，翻译成更清楚、更稳、更低风险的沟通动作。

它主要处理两类场景：

- `To:` 你准备发出去的话，先做发前预检
- `Re领导:` / `Re同事:` 别人发给你的登位话术，给你一版低风险回复

## 现在能做什么

- 飞书私聊 bot
- 默认使用飞书长连接收事件，不需要公网回调地址或内网穿透
- 本地老登话术库优先，复杂表达再走可配置模型后端
- 支持轻量模糊匹配，不只是死关键词命中
- 支持三种输入前缀：
  - `To:`
  - `Re领导:`
  - `Re同事:`

## 交互方式

### 1. 发前预检

```text
To: 今晚必须改完，别再给我找理由。
```

机器人会返回：

- 风险等级
- 一句简短提醒
- 标准版
- 更坚定版
- 必要时的一句补充建议

### 2. 来话应对

```text
Re领导: 别跟我解释了，今晚必须给我结果。
```

或：

```text
Re同事: 都是自己人，别老讲边界感。
```

机器人会返回：

- 场景
- 你的即时目标
- 一版建议回复
- 一版更坚定回复
- 一条后续动作

## 为什么用长连接

这个项目默认用飞书 `long_connection` 模式收事件。

好处很直接：

- 不需要你自己搭公网回调地址
- 不需要 `cloudflared`、`ngrok` 或其他内网穿透
- 机器开着、能联网，就能持续收飞书消息

如果你确实想走传统回调，也保留了 `webhook` 模式。

## 项目结构

- `anti-laodeng/`
  反老登 skill 本体和参考资料
- `feishu_bot_mvp/server.py`
  主入口，负责飞书接入、前缀路由、复杂后端调用
- `feishu_bot_mvp/fast_path_bank.py`
  本地老登话术库、规则库、模糊匹配
- `feishu_bot_mvp/counter_strategy_bank.py`
  来话应对策略和回复格式
- `feishu_bot_mvp/review_schema.json`
  发前预检结构化输出 schema
- `feishu_bot_mvp/counter_schema.json`
  来话应对结构化输出 schema
- `howtocounterlaodeng.txt`
  来话应对原则与策略参考
- `whatislaodeng.txt`
  老登行为与典型话术整理

## 安装

```bash
python3 -m pip install -r requirements.txt
```

如果你想自己单独装官方飞书 SDK，也就是：

```bash
python3 -m pip install lark-oapi
```

## 最小启动配置

最少需要这些环境变量：

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
export FEISHU_EVENT_MODE="long_connection"
export COMPLEX_REVIEW_PROVIDER="codex"
```

然后启动：

```bash
python3 feishu_bot_mvp/server.py
```

## 复杂表达后端

本地模板机会优先处理高频老登话术。

如果没命中，就走复杂后端。现在支持三种：

- `codex`
- `openrouter`
- `compatible`

### 1. 走 Codex

```bash
export COMPLEX_REVIEW_PROVIDER="codex"
export CODEX_MODEL="gpt-5.3-codex-spark"
python3 feishu_bot_mvp/server.py
```

### 2. 走 OpenRouter

```bash
export COMPLEX_REVIEW_PROVIDER="openrouter"
export OPENROUTER_API_KEY="or_xxx"
export OPENROUTER_MODEL="openai/gpt-4.1-mini"
python3 feishu_bot_mvp/server.py
```

### 3. 走兼容 OpenAI Chat Completions 的第三方接口

适合你想接自己的推理服务，或者接别家兼容接口，例如一些 `interns1` 风格的模型网关。

```bash
export COMPLEX_REVIEW_PROVIDER="compatible"
export COMPATIBLE_CHAT_URL="https://your-endpoint.example.com/v1/chat/completions"
export COMPATIBLE_API_KEY="sk-xxx"
export COMPATIBLE_MODEL="interns1/your-fast-model"
python3 feishu_bot_mvp/server.py
```

完整变量见：

- [feishu_bot_mvp/.env.example](feishu_bot_mvp/.env.example)

## 飞书侧需要开什么

至少需要：

- Bot 能力
- 事件订阅
- `im.message.receive_v1`
- bot 发消息相关权限

如果你走长连接，关键是：

- 飞书应用本身开了事件订阅
- 当前测试账号已经安装这个应用
- 机器人能和你私聊

## 本地测试

### 单次发前预检

```bash
python3 feishu_bot_mvp/server.py --review "To: 今晚必须改完，别再给我找理由。"
```

### 单次来话应对

```bash
python3 feishu_bot_mvp/server.py --review "Re领导: 别跟我解释了，今晚必须给我结果。"
python3 feishu_bot_mvp/server.py --review "Re同事: 都是自己人，别老讲边界感。"
```

### 查看本地老登话术库规模

```bash
python3 feishu_bot_mvp/server.py --fastpath-stats
```

## 飞书里怎么用

私聊 bot，直接发这三种格式之一：

- `To: ...`
- `Re领导: ...`
- `Re同事: ...`

例子：

```text
To: 这个事情为什么还没搞定？我上次已经说得很清楚了。
```

```text
Re领导: 先别解释，今晚先给我结果。
```

```text
Re同事: 大家都是自己人，这种小事别分那么清。
```

## 当前实现思路

核心流程是：

1. 飞书收到私聊消息
2. `server.py` 根据前缀判断是 `To` 还是 `Re`
3. 本地老登话术库先尝试命中
4. 命中则本地直接生成结果
5. 未命中则交给复杂后端
6. 最终把结果压成简洁文本回给飞书

也就是说，这个项目不是“人格评判器”，而是一个：

- 发前自检器
- 来话拆招器
- 低风险沟通改写器

## 常见问题

### 为什么有时候很快，有时候慢

因为常见话术会直接命中本地老登话术库，几乎秒回；复杂表达才会走模型后端。

### 为什么默认推荐长连接

因为对个人开发者更友好，不需要公网地址，也不需要一直维护 tunnel。

### 为什么不做自动代发

当前 MVP 故意只做“建议与改写”，不替你直接发给别人，避免误发和过度自动化。


