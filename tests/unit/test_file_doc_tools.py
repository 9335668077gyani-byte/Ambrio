import pytest, asyncio, sys, os, tempfile
sys.path.insert(0, r'C:\MY PROJECTS\Ambrio')

from ambrio.router.tools.file_tool import file_read, file_write, file_list, file_search
from ambrio.router.tools.doc_tool  import doc_read

@pytest.mark.asyncio
async def test_file_write_and_read():
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False, mode='w') as f:
        tmp = f.name
    result = await file_write(tmp, 'Hello Ambrio!')
    assert result['success'] is True
    read_result = await file_read(tmp)
    assert 'Hello Ambrio!' in read_result['content']
    os.unlink(tmp)

@pytest.mark.asyncio
async def test_file_list_returns_entries():
    result = await file_list('C:\\MY PROJECTS\\Ambrio')
    assert 'entries' in result
    assert result['total'] > 0

@pytest.mark.asyncio
async def test_file_read_not_found():
    result = await file_read('C:\\nonexistent_file_xyz.txt')
    assert 'error' in result

@pytest.mark.asyncio
async def test_doc_read_txt():
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False, mode='w') as f:
        f.write('This is a test document.')
        tmp = f.name
    result = await doc_read(tmp)
    assert 'content' in result
    assert 'This is a test document.' in result['content']
    os.unlink(tmp)
