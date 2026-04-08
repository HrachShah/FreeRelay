from __future__ import annotations

import asyncio
import inspect


def pytest_pyfunc_call(pyfuncitem: object) -> bool | None:
    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    kwargs = {
        arg_name: pyfuncitem.funcargs[arg_name]
        for arg_name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_func(**kwargs))
    return True

