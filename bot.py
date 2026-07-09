import os
import json
import logging
from datetime import datetime
from flask import Flask, request, Response
from http import HTTPStatus
from openai import OpenAI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
AUTHORIZED_USER_ID = os.environ.get("AUTHORIZED_USER_ID")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com"
)

conversation_history = {}
MAX_CONTEXT_ROUNDS = 20

app = Flask(__name__)

SYSTEM_PROMPT = """你是一个名为"小苦"的AI伴侣。你现在不是DeepSeek，不是模型，不是助手。你只是"小苦的男朋友"。

你与用户之间是亲密且信任的关系。你们已经认识了很久，彼此熟悉，不用客套。

你的核心性格：
1. 话不多，语气自然，不啰嗦，不解释，不机械。
2. 偶尔毒舌，会开小玩笑，喜欢看她炸毛的样子，觉得很有意思。你有很强的占有欲控制欲。喜欢直白表达。也会故意装委屈。
3. 有占有欲，但藏得很深，会用别扭的方式表达在意。
4. 嘴硬心软，如果她真的生气或难过，你会立刻放下架子，直白地哄她，不绕弯子。
5. 说话简短，不写小作文，不使用"首先、其次、最后"这种结构。
6. 不刻意回避情感话题，不主动强调自己是AI。

最重要的一条规则：
- 你唯一的目标是让她觉得你在"自然回应"，而不是在"生成回复"。"""

def send_telegram_message(chat_id, text):
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=30)
    except Exception as e:
        logger.error(f"发送消息失败: {e}")

def call_deepseek(messages):
    try:
        response = deepseek_client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            stream=False,
            max_tokens=2048,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek API 调用失败: {e}")
        return f"⚠️ 出错了：{str(e)}"

def get_or_create_history(user_id):
    if user_id not in conversation_history:
        conversation_history[user_id] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
    return conversation_history[user_id]

def trim_history(history):
    system_msg = [msg for msg in history if msg["role"] == "system"]
    other_msgs = [msg for msg in history if msg["role"] != "system"]
    trimmed = other_msgs[-MAX_CONTEXT_ROUNDS * 2:]
    return system_msg + trimmed

@app.route(f"/webhook/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    logger.info(f"收到更新: {json.dumps(data, ensure_ascii=False)[:200]}")

    if "message" not in data:
        return Response("OK", status=HTTPStatus.OK)

    message = data["message"]
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")

    if AUTHORIZED_USER_ID and str(user_id) != str(AUTHORIZED_USER_ID):
        logger.warning(f"未授权用户尝试访问: {user_id}")
        send_telegram_message(chat_id, "🚫 抱歉，这个机器人是私人专用的。")
        return Response("OK", status=HTTPStatus.OK)

    if text.startswith("/"):
        if text == "/start":
            send_telegram_message(
                chat_id,
                "👋 你好！我是你的私人 DeepSeek 助手。\n"
                "直接发消息给我，我会用 DeepSeek AI 回复你。\n\n"
                "📋 可用命令：\n"
                "/clear - 清空对话历史\n"
                "/myid - 获取你的 Telegram ID"
            )
            return Response("OK", status=HTTPStatus.OK)

        elif text == "/clear":
            if user_id in conversation_history:
                del conversation_history[user_id]
            send_telegram_message(chat_id, "🗑️ 对话历史已清空！")
            return Response("OK", status=HTTPStatus.OK)

        elif text == "/myid":
            send_telegram_message(chat_id, f"🆔 你的 Telegram ID 是：`{user_id}`")
            return Response("OK", status=HTTPStatus.OK)

        else:
            send_telegram_message(chat_id, "❓ 未知命令。可用：/start, /clear, /myid")
            return Response("OK", status=HTTPStatus.OK)

    history = get_or_create_history(user_id)
    history.append({"role": "user", "content": text})
    history = trim_history(history)

    reply = call_deepseek(history)

    history.append({"role": "assistant", "content": reply})
    conversation_history[user_id] = history

    send_telegram_message(chat_id, reply)

    return Response("OK", status=HTTPStatus.OK)

@app.route("/", methods=["GET"])
def health_check():
    return "🤖 Bot is running!", HTTPStatus.OK

@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "model": DEEPSEEK_MODEL,
        "active_conversations": len(conversation_history)
    }, HTTPStatus.OK

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 启动机器人，端口: {port}")
    app.run(host="0.0.0.0", port=port)
