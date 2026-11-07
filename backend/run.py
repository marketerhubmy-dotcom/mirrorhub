import asyncio
import sys
import uvicorn
from app.core.config import settings

# Windows Python 3.12+ defaults to ProactorEventLoop but uvicorn with reload=True
# can revert to SelectorEventLoop, breaking asyncio.create_subprocess_exec.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
