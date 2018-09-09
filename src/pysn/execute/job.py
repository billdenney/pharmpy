# -*- encoding: utf-8 -*-

import asyncio
import locale
import os
from asyncio.subprocess import PIPE
from contextlib import closing
from queue import Empty
from queue import Queue


class AsyncProcess:
    """An asynchronous process."""

    def __init__(self, loop, *command):
        self.loop = loop
        self.command = command
        self.stdout_lines = list()
        self.stdout_queue = Queue()
        self.complete = False

    def run(self):
        with closing(self.loop):
            self.loop.run_until_complete(self._async_exec(*self.command))
        self.stdout
        self.complete = True

    @property
    def stdout(self):
        try:
            line = self.stdout_queue.get_nowait()
        except Empty:
            return None
        else:
            self.stdout_lines += [line]
            return line

    async def _async_exec(self, *command):
        # ref: https://stackoverflow.com/a/20697159
        process = await asyncio.create_subprocess_exec(*command, stdout=PIPE)
        async for line in process.stdout:
            decoded_line = line.decode(locale.getpreferredencoding(False))
            self.stdout_queue.put(decoded_line)
        return await process.wait()


class Job:
    """A job of an Engine (running in an Environment)."""

    def __init__(self, *commands):
        if os.name == 'nt':
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(self.loop)
        else:
            loop = asyncio.get_event_loop()

        self.processes = [None]*len(commands)
        for i, command in enumerate(commands):
            proc = AsyncProcess(loop, *command)
            self.processes[i] = proc
            proc.run()

    @property
    def complete(self):
        """True of (all of) job is complete."""
        return all(process.complete for process in self.processes)