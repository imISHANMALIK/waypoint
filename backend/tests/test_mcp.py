"""Real MCP stdio handshake and HTTP round trip, against an isolated API."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]


def test_mcp_protocol_round_trip(tmp_path):
    with socket.socket() as socket_:
        socket_.bind(('127.0.0.1', 0))
        port = socket_.getsockname()[1]
    env = {**os.environ, 'WAYPOINT_DATA_DIR': str(tmp_path), 'WAYPOINT_MODEL':'', 'WAYPOINT_API_URL':f'http://127.0.0.1:{port}'}
    backend = subprocess.Popen([sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if httpx.get(env['WAYPOINT_API_URL']+'/api/health',timeout=.2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(.05)
        else:
            raise AssertionError('Isolated API did not start')

        async def exercise():
            params = StdioServerParameters(command=sys.executable,args=[str(ROOT/'backend/mcp_server.py')],env=env)
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert len(tools.tools) == 6
                    snapshot = await session.call_tool('inspect_warehouse',{})
                    assert not snapshot.isError
                    assert json.loads(snapshot.content[0].text)['metrics']['total'] == 48
                    result = await session.call_tool('propose_plan',{'objective':'throughput'})
                    assert not result.isError
                    plan = json.loads(result.content[0].text)
                    assert plan['status'] == 'pending'
                    decision = await session.call_tool('review_plan',{'plan_id':plan['id'],'approved':False})
                    assert not decision.isError
                    assert json.loads(decision.content[0].text)['run']['status'] == 'rejected'
                    resources = await session.list_resources()
                    assert len(resources.resources) == 2
                    prompts = await session.list_prompts()
                    assert prompts.prompts[0].name == 'investigate_warehouse'
        asyncio.run(exercise())
    finally:
        backend.terminate()
        backend.wait(timeout=10)
