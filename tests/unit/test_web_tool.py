import pytest
import asyncio
import sys
sys.path.insert(0, r'C:\MY PROJECTS\Ambrio')

from ambrio.router.tools.web_tool import web_search, web_read, reddit_search, github_search

@pytest.mark.asyncio
async def test_web_search_returns_results():
    result = await web_search('Python programming')
    assert 'results' in result
    assert 'query' in result
    assert result['query'] == 'Python programming'

@pytest.mark.asyncio
async def test_web_read_returns_content():
    result = await web_read('https://example.com')
    assert 'content' in result
    assert len(result['content']) > 10

@pytest.mark.asyncio
async def test_reddit_search_structure():
    result = await reddit_search('python tips')
    assert 'posts' in result
    assert 'query' in result

@pytest.mark.asyncio
async def test_github_search_repos():
    result = await github_search('ollama python', 'repositories', 3)
    assert 'results' in result
    if not result.get('error'):
        assert result['total'] >= 0
