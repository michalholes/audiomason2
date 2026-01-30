"""Parallel book processor - process multiple books concurrently."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from audiomason.core import ProcessingContext, PipelineExecutor, PluginLoader


class ParallelProcessor:
    """Process multiple books in parallel.

    Manages concurrent book processing with resource limits.
    """

    def __init__(
        self,
        pipeline_executor: PipelineExecutor,
        max_concurrent: int = 2,
    ) -> None:
        """Initialize parallel processor.

        Args:
            pipeline_executor: Pipeline executor to use
            max_concurrent: Maximum concurrent books
        """
        self.pipeline_executor = pipeline_executor
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def process_book(self, context: ProcessingContext, pipeline_path: Path) -> ProcessingContext:
        """Process single book with semaphore.

        Args:
            context: Processing context
            pipeline_path: Pipeline YAML path

        Returns:
            Completed context
        """
        async with self.semaphore:
            return await self.pipeline_executor.execute_from_yaml(pipeline_path, context)

    async def process_batch(
        self,
        contexts: list[ProcessingContext],
        pipeline_path: Path,
        progress_callback: Any = None,
    ) -> list[ProcessingContext]:
        """Process multiple books in parallel.

        Args:
            contexts: List of processing contexts
            pipeline_path: Pipeline YAML path
            progress_callback: Optional callback for progress updates

        Returns:
            List of completed contexts
        """
        # Create tasks
        tasks = []
        for context in contexts:
            task = self.process_book(context, pipeline_path)
            tasks.append(task)

        # Process with progress tracking
        results = []
        
        for i, task in enumerate(asyncio.as_completed(tasks)):
            try:
                result = await task
                results.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, len(tasks), result)
                    
            except Exception as e:
                # Log error but continue with other books
                print(f"Error processing book: {e}")
                continue

        return results


class BatchQueue:
    """Queue manager for batch processing.

    Allows adding books to queue while processing continues.
    """

    def __init__(
        self,
        pipeline_executor: PipelineExecutor,
        pipeline_path: Path,
        max_concurrent: int = 2,
    ) -> None:
        """Initialize batch queue.

        Args:
            pipeline_executor: Pipeline executor
            pipeline_path: Pipeline YAML path
            max_concurrent: Maximum concurrent books
        """
        self.pipeline_executor = pipeline_executor
        self.pipeline_path = pipeline_path
        self.max_concurrent = max_concurrent
        self.queue: asyncio.Queue[ProcessingContext] = asyncio.Queue()
        self.results: list[ProcessingContext] = []
        self.running = False

    async def add(self, context: ProcessingContext) -> None:
        """Add book to queue.

        Args:
            context: Processing context
        """
        await self.queue.put(context)

    async def worker(self) -> None:
        """Worker task - processes books from queue."""
        while self.running:
            try:
                # Get book from queue (with timeout)
                context = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                
                # Process book
                result = await self.pipeline_executor.execute_from_yaml(
                    self.pipeline_path, context
                )
                
                self.results.append(result)
                self.queue.task_done()
                
            except asyncio.TimeoutError:
                # No books in queue, continue
                continue
            except Exception as e:
                print(f"Worker error: {e}")
                continue

    async def start(self) -> None:
        """Start processing queue."""
        self.running = True
        
        # Start worker tasks
        workers = []
        for _ in range(self.max_concurrent):
            worker = asyncio.create_task(self.worker())
            workers.append(worker)
        
        # Wait for all tasks to complete
        await self.queue.join()
        
        # Stop workers
        self.running = False
        await asyncio.gather(*workers, return_exceptions=True)

    def get_results(self) -> list[ProcessingContext]:
        """Get all processed results.

        Returns:
            List of completed contexts
        """
        return self.results.copy()
