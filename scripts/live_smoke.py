"""Opt-in live check. Four Gemini calls; does not prove factual accuracy."""
import argparse
import asyncio
import json
import os
import sys
from urllib.parse import urlsplit

import httpx


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Public YouTube Shorts URL')
    parser.add_argument('--timestamp', default='00:05')
    parser.add_argument('--allow-quota-use', action='store_true')
    args = parser.parse_args()
    endpoint = os.environ.get('YOUTUBE_MCP_URL', '')
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        sys.exit('Set YOUTUBE_MCP_URL securely to the deployed HTTPS MCP endpoint.')
    if not args.allow_quota_use:
        sys.exit('No requests sent. Confirm free quota/billing, then pass --allow-quota-use (4 video calls).')
    async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
        protocol = '2025-11-25'
        headers = {'Accept': 'application/json, text/event-stream'}
        counter = 0
        async def rpc(method, params):
            nonlocal counter
            counter += 1
            response = await client.post(endpoint, headers=headers, json={
                'jsonrpc': '2.0', 'id': counter, 'method': method, 'params': params})
            if response.status_code != 200:
                sys.exit(f'MCP HTTP {response.status_code}; endpoint omitted.')
            session = response.headers.get('mcp-session-id')
            if session:
                headers['Mcp-Session-Id'] = session
            result = response.json()
            if 'error' in result:
                sys.exit('MCP returned a protocol error; endpoint omitted.')
            return result['result']
        init = await rpc('initialize', {'protocolVersion': protocol, 'capabilities': {},
                                        'clientInfo': {'name': 'live-smoke', 'version': '1'}})
        headers['MCP-Protocol-Version'] = init['protocolVersion']
        notification = await client.post(endpoint, headers=headers, json={
            'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        if notification.status_code != 202:
            sys.exit('Initialization notification failed.')
        tools = await rpc('tools/list', {})
        assert {x['name'] for x in tools['tools']} >= {
            'analyze_youtube_video', 'inspect_youtube_moment', 'youtube_mcp_status'}
        print(json.dumps(await rpc('tools/call', {'name': 'youtube_mcp_status', 'arguments': {}}), ensure_ascii=False))
        for label, name, arguments in [
            ('speech', 'analyze_youtube_video', {'url': args.url, 'mode': 'quick', 'focus': 'Отдельно передай речь. Отметь неразборчивые слова.'}),
            ('scenes', 'analyze_youtube_video', {'url': args.url, 'mode': 'visual', 'focus': 'Опиши только визуальные сцены с таймкодами.'}),
            ('text', 'analyze_youtube_video', {'url': args.url, 'mode': 'visual', 'focus': 'Выпиши надписи на экране и их таймкоды. Не додумывай неразборчивое.'}),
            ('moment', 'inspect_youtube_moment', {'url': args.url, 'timestamp': args.timestamp, 'question': 'Что видно, слышно и написано в этот момент?'}),
        ]:
            result = await rpc('tools/call', {'name': name, 'arguments': arguments})
            print(json.dumps({'check': label, 'result': result}, ensure_ascii=False))
            if result.get('isError'):
                sys.exit('Stopped after first tool failure; remaining quota not used.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (httpx.HTTPError, ValueError, KeyError, AssertionError):
        sys.exit('Live check failed; raw exception omitted to protect the endpoint.')
