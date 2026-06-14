"""WeChat MCP Server — FastAPI 主入口。"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

try:
    from .config import WECHAT_TOKEN, MCP_PORT
    from .wechat import WeChatProtocol
    from .queue import MessageQueue
    from .mcp_handler import MCPHandler
except ImportError:
    # Allows `python wechat_mcp_server/server.py` during local setup.
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from wechat_mcp_server.config import WECHAT_TOKEN, MCP_PORT
    from wechat_mcp_server.wechat import WeChatProtocol
    from wechat_mcp_server.queue import MessageQueue
    from wechat_mcp_server.mcp_handler import MCPHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WeChat MCP Server")
mq = MessageQueue()
handler = MCPHandler(mq)


# ─── 微信 webhook ─────────────────────────────────

@app.get("/wechat")
async def wechat_verify(
    signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
):
    """微信 token 验证。"""
    if WeChatProtocol.verify_signature(WECHAT_TOKEN, signature, timestamp, nonce):
        return PlainTextResponse(echostr)
    return PlainTextResponse("invalid signature", status_code=403)


@app.post("/wechat")
async def wechat_callback(request: Request):
    """接收微信消息推送。"""
    body = await request.body()
    xml_str = body.decode("utf-8")

    msg = WeChatProtocol.parse_message(xml_str)
    if msg:
        queued = mq.push(
            user_openid=msg["from_user"],
            msg_type=msg["msg_type"],
            content=msg["content"],
            msg_id=msg["msg_id"],
        )
        if queued:
            logger.info(f"收到消息: {msg['from_user']} -> {msg['content'][:30]}")
        else:
            logger.info(f"忽略重复消息: {msg['from_user']} -> {msg['content'][:30]}")

    return PlainTextResponse("success")


# ─── MCP JSON-RPC 端点 ────────────────────────────

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC 2.0 入口。"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    req_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    result_or_error = await handler.handle_async(method, params)

    response = {"jsonrpc": "2.0", "id": req_id}
    if "error" in result_or_error:
        response["error"] = result_or_error["error"]
    else:
        response["result"] = result_or_error

    return JSONResponse(response)


@app.get("/health")
async def health():
    return {"status": "ok", "queue_size": mq.size}


# ─── 启动 ────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting WeChat MCP Server on port {MCP_PORT}")
    uvicorn.run(app, host="127.0.0.1", port=MCP_PORT, log_level="info")
