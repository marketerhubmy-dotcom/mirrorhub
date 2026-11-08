import asyncio
import sys
import uvicorn
from app.core.config import settings

# Windows Python 3.12+ defaults to ProactorEventLoop but uvicorn with reload=True
# can revert to SelectorEventLoop, breaking asyncio.create_subprocess_exec.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    from app.core.security import effective_bind_host
    uvicorn.run(
        "app.main:app",
        host=effective_bind_host(settings.host, settings.allow_remote_bind),
        port=settings.port,
        reload=False,
        ws_per_message_deflate=False,
    )
