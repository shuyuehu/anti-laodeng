# anti-laodeng

一个接入飞书的“反老登”机器人原型，支持两类场景：

- `To:` 发前预检，帮你把准备发出去的话改得更清楚、不压人
- `Re领导:` / `Re同事:` 来话应对，给出低风险回复和更坚定版本

## 当前能力

- 飞书私聊 bot
- 默认使用飞书长连接接收事件，不需要公网回调地址
- 本地模板机优先，复杂表达再走可配置模型后端
- 支持 `To:`、`Re领导:`、`Re同事:`

## 项目结构

- `anti-laodeng/`：skill 与参考资料
- `feishu_bot_mvp/server.py`：主服务入口
- `feishu_bot_mvp/fast_path_bank.py`：本地模板机与模糊匹配
- `feishu_bot_mvp/counter_strategy_bank.py`：来话应对策略与回复格式
- `feishu_bot_mvp/*.json`：结构化输出 schema

## 安装

```bash
python3 -m pip install -r requirements.txt
```

## 环境变量

最少需要：

```bash
export FEISHU_APP_ID="cli_xxx"
export FEISHU_APP_SECRET="xxx"
export FEISHU_EVENT_MODE="long_connection"
export COMPLEX_REVIEW_PROVIDER="codex"
```

如果复杂表达想改走其他后端，也支持：

- `openrouter`
- `compatible`

可参考：

- `feishu_bot_mvp/.env.example`

## 启动

```bash
python3 feishu_bot_mvp/server.py
```

## 本地测试

```bash
python3 feishu_bot_mvp/server.py --review "To: 今晚必须改完，别再给我找理由。"
python3 feishu_bot_mvp/server.py --review "Re领导: 别跟我解释了，今晚必须给我结果。"
python3 feishu_bot_mvp/server.py --review "Re同事: 都是自己人，别老讲边界感。"
```

## 飞书使用方式

私聊 bot，直接发：

- `To: ...`
- `Re领导: ...`
- `Re同事: ...`

机器人会返回更精简的可直接使用话术。
