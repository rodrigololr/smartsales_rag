"""Test-wide setup shared by unit and integration suites."""

import asyncio
import sys

if sys.platform == "win32":
    # psycopg's async mode cannot run on the default ProactorEventLoop (Windows dev boxes).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
