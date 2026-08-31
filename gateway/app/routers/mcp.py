from __future__ import annotations

import ast
import logging
import operator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models.schemas import MCPRequest, MCPResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp"])

_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for up-to-date information. Returns a list of relevant snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-10)",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "calculator",
        "description": "Safely evaluate a mathematical expression. Supports +, -, *, /, **, %, and parentheses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A math expression, e.g. '2 * (3 + 4) / 7'",
                }
            },
            "required": ["expression"],
        },
    },
]

_SAFE_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> float:
    tree = ast.parse(expr.strip(), mode="eval")

    def _eval(node: ast.expr) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp):
            op_fn = _SAFE_OPS.get(type(node.op))
            if op_fn is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op_fn(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op_fn = _SAFE_OPS.get(type(node.op))
            if op_fn is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            return op_fn(_eval(node.operand))
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    return _eval(tree)


async def _handle_tools_list(_params: dict) -> dict:
    return {"tools": _TOOLS}


async def _handle_tools_call(params: dict) -> dict:
    name = params.get("name")
    arguments = params.get("arguments", {})

    if name == "web_search":
        query = arguments.get("query", "")
        num = min(int(arguments.get("num_results", 3)), 10)
        results = [
            {
                "title": f"Result {i + 1} for: {query}",
                "url": f"https://example.com/result-{i + 1}",
                "snippet": (
                    f"This is a stub result #{i + 1} for the query '{query}'. "
                    "In production, wire this to a real search API such as Brave or SerpAPI."
                ),
            }
            for i in range(num)
        ]
        text = "\n\n".join(
            f"[{r['title']}]({r['url']})\n{r['snippet']}" for r in results
        )
        return {"content": [{"type": "text", "text": text}]}

    if name == "calculator":
        expr = arguments.get("expression", "")
        try:
            result = _safe_eval(expr)
            return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            }

    raise ValueError(f"Unknown tool: {name}")


_DISPATCH = {
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


@router.post("")
async def mcp_endpoint(body: MCPRequest) -> JSONResponse:
    handler = _DISPATCH.get(body.method)
    if handler is None:
        error_resp = MCPResponse(
            id=body.id,
            error={"code": -32601, "message": f"Method not found: {body.method}"},
        )
        return JSONResponse(content=error_resp.model_dump(), status_code=200)

    try:
        result = await handler(body.params)
        resp = MCPResponse(id=body.id, result=result)
        return JSONResponse(content=resp.model_dump(), status_code=200)
    except ValueError as exc:
        error_resp = MCPResponse(
            id=body.id,
            error={"code": -32602, "message": str(exc)},
        )
        return JSONResponse(content=error_resp.model_dump(), status_code=200)
    except Exception as exc:
        logger.exception("MCP handler error")
        error_resp = MCPResponse(
            id=body.id,
            error={"code": -32603, "message": "Internal error"},
        )
        return JSONResponse(content=error_resp.model_dump(), status_code=200)
