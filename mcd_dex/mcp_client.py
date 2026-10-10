#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦图鉴 · 麦当劳 MCP 客户端（零第三方依赖版）

只做三件事：
1. initialize 握手
2. tools/list 拉取工具清单
3. tools/call 调用工具（本文仅用到 list-nutrition-foods 做图鉴同步）

凭据安全：Token 一律读环境变量 MCD_MCP_TOKEN，绝不硬编码。
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

MCP_ENDPOINT = "https://mcp.mcd.cn"


class McHttpClient:
    """极简 MCP Streamable HTTP 客户端（JSON-RPC over HTTP POST）。"""

    def __init__(self, endpoint: str = MCP_ENDPOINT, token: Optional[str] = None):
        self.endpoint = endpoint
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "")
        self._session_id: Optional[str] = None
        if not self.token:
            raise RuntimeError(
                "未检测到 MCD_MCP_TOKEN 环境变量。"
                "请先在 https://open.mcd.cn/mcp 申请 Token 后：export MCD_MCP_TOKEN=你的Token"
            )

    # ---------- 底层 ----------
    def _post(self, payload: dict, with_session: bool = True) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
        }
        if with_session and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self._session_id = sid
            body = resp.read().decode("utf-8")
        return self._parse(body)

    @staticmethod
    def _parse(body: str) -> dict:
        """兼容纯 JSON 与 SSE（text/event-stream）两种返回体。"""
        body = body.strip()
        if body.startswith("{"):
            return json.loads(body)
        # SSE：取第一个 data: 行
        for line in body.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    return json.loads(chunk)
        raise RuntimeError("无法解析 MCP 返回体：%s..." % body[:200])

    # ---------- 协议层 ----------
    def initialize(self) -> dict:
        resp = self._post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "mcd-dex", "version": "1.0.0"},
            },
        })
        # 通知服务端初始化完成（规范要求）
        try:
            self._post({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }, with_session=True)
        except Exception:
            pass  # 部分服务端对 notification 不回包，忽略
        return resp

    def list_tools(self) -> list:
        resp = self._post({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
        })
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> dict:
        resp = self._post({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })
        if "error" in resp:
            raise RuntimeError("MCP 工具调用失败：%s" % resp["error"])
        return resp.get("result", {})


# ============================================================
# 自测：python -m mcd_dex.mcp_client
# ============================================================

if __name__ == "__main__":
    client = McHttpClient()
    print("· 握手中 ...")
    init = client.initialize()
    info = init.get("result", {}).get("serverInfo", {})
    print("✅ 已连接：%s %s" % (info.get("name", "?"), info.get("version", "?")))
    print("· 拉取工具清单 ...")
    tools = client.list_tools()
    print("✅ 共 %d 个工具：" % len(tools))
    for t in tools:
        print("   - %s" % t.get("name"))
