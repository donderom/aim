import asyncio
import queue
import pathlib

import click
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import watchdog.events as events

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from aim._sdk.repo import Repo


class SourceFileChangeHandler(FileSystemEventHandler):
    def __init__(self, src_dir: pathlib.Path, q):
        self.src_dir = src_dir
        self.queue = q

    def on_moved(self, event):
        if not event.is_directory:
            self.queue.put(event)

    def on_created(self, event):
        if not event.is_directory:
            self.queue.put(event)

    def on_deleted(self, event):
        if not event.is_directory:
            self.queue.put(event)

    def on_modified(self, event):
        if not event.is_directory:
            self.queue.put(event)


class PackageSourceWatcher:
    def __init__(self, repo: 'Repo', package_name: str, src_dir: str):
        self.repo = repo
        self.package_name = package_name
        self.package = repo.storage_engine.dev_package(package_name)
        self.src_dir = pathlib.Path(src_dir)

        self.queue = queue.Queue()
        self.observer = None

    async def watch_events(self):
        while True:
            fs_events = []
            while not self.queue.empty():
                fs_events.append(self.queue.get())
            with self.repo.storage_engine.write_batch(0):
                for fs_event in fs_events:
                    try:
                        file = pathlib.Path(fs_event.src_path)
                        file_path = str(file.relative_to(self.src_dir))
                        click.echo(f'Detected change in file \'{file_path}\'. Syncing.')

                        if fs_event.event_type in (events.EVENT_TYPE_CREATED, events.EVENT_TYPE_MODIFIED):
                            with file.open('r') as fh:
                                contents = fh.read()
                                self.package.sync(str(file_path), contents)
                        elif fs_event.event_type == events.EVENT_TYPE_DELETED:
                            self.package.remove(str(file_path))
                        elif fs_event == events.EVENT_TYPE_MOVED:
                            dest_path = pathlib.Path(fs_event.dest_path).relative_to(self.src_dir)
                            self.package.move(file_path, dest_path)
                    except Exception:
                        pass

            await asyncio.sleep(5)

    def start(self):
        self.observer = Observer()
        event_hanlder = SourceFileChangeHandler(self.src_dir, self.queue)
        self.observer.schedule(event_hanlder, self.src_dir, recursive=True)
        self.observer.start()
        try:
            asyncio.get_event_loop().run_until_complete(self.watch_events())
        except KeyboardInterrupt:
            self.observer.stop()

        self.observer.join()
        self.observer = None

    def initialize(self):
        with self.repo.storage_engine.write_batch(0):
            click.echo(f'Initializing package \'{self.package_name}\'.')
            for file_path in self.src_dir.glob('**/*'):
                file_name = file_path.relative_to(self.src_dir)
                if file_path.is_file():
                    with file_path.open('r') as fh:
                        self.package.sync(str(file_name), fh.read())
            self.package.install()
