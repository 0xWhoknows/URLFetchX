# -*- coding: utf-8 -*- 
# @Author: Who Knows [https://github.com/0xWhoknows]
# @Date: 2025-06-22
# @Version: 1.0.0
# @Description: A simple URL processor that fetches URLs and processes them with a CPU-heavy task.      
# @Usage: python urlfetchx.py 
# @courtesy: https://github.com/0xWhoknows/urlfetchx
# @thanks: cursor.sh  @stack overflow  


import asyncio
import aiofiles
import aiohttp
import sys
import time
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Optional, Dict


class Colors:
    '''
    Colors for console output.
    '''
    GREEN = '\033[92m'
    WHITE = '\033[97m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    ENDC = '\033[0m'


@dataclass(frozen=True)
class NetworkResult:
    '''
    A dataclass for storing the result of a URL fetch.
    '''
    url: str
    status: int
    success: bool
    content: Optional[str] = None
    error_message: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    elapsed_time: Optional[float] = None
    redirected: bool = False
    attempts: int = 0
    content_type: Optional[str] = None
    response_size: Optional[int] = None
    error_code: Optional[int] = None


@dataclass(frozen=True)
class ProcessedResult:
    '''
    A dataclass for storing the result of a URL processing.
    '''
    url: str
    status: int
    success: bool
    processed_data: Optional[str] = None
    error_message: Optional[str] = None
    processing_time: Optional[float] = None
    processed_successfully: bool = True
    summary: Optional[str] = None
    metadata: Optional[dict] = None
    error_code: Optional[int] = None


class URLProcessor:
    MAX_CONCURRENT_REQUESTS = 100 # max concurrent requests
    CPU_WORKERS = None          # auto detect cores
    RETRY_LIMIT = 0            # no retries
    RETRY_DELAY = 0.5          # retry delay
    BACKPRESSURE_THRESHOLD = 300 # backpressure threshold
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB limit
    QUEUE_MAXSIZE = 1000  # Prevent unbounded queue growth

    def __init__(self, filename: str):
        '''
        Initialize the URLProcessor.
        '''
        self.filename = filename
        self.url_queue = asyncio.Queue()
        self.retry_queue = asyncio.Queue()
        self.network_result_queue = asyncio.Queue()
        self.processed_result_queue = asyncio.Queue()
        self.lock = asyncio.Lock()
        self.stats = {'processed': 0, 'alive': 0, 'dead': 0, 'retries': 0, 'total': 0}
        self.executor = None
        self.stop_event = asyncio.Event()
        self.headers_list = [
            {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36'},
            {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/121.0.0.0 Safari/537.36'},
            {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0 Safari/537.36'},
            {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'},
            {'User-Agent': 'curl/7.79.1'}
        ]

    async def load_urls(self):
        '''
        Load URLs from a file.
        '''
        async with aiofiles.open(self.filename, 'r', encoding='utf-8') as f:
            async for line in f:
                url = line.strip()
                if url:
                    await self.url_queue.put((url, 0))
                    self.stats['total'] += 1
        print(f"{Colors.YELLOW}Loaded {self.stats['total']} URLs.{Colors.ENDC}")

    async def fetch_worker(self, session):
        '''
        Fetch URLs from the queue.
        '''
        while True:
            if self.url_queue.qsize() > self.BACKPRESSURE_THRESHOLD:
                await asyncio.sleep(0.1)  # backpressure pause

            try:
                url, retries = await self.url_queue.get()
                start = time.perf_counter()
                result = await self.fetch_url(session, url, retries)
                elapsed = time.perf_counter() - start

                # if fetch succeeded
                if result.success:
                    result = NetworkResult(
                        url=result.url,
                        status=result.status,
                        success=result.success,
                        content=result.content,
                        error_message=result.error_message,
                        elapsed_time=elapsed,
                        attempts=retries
                    )

                await self.network_result_queue.put(result)
            except asyncio.CancelledError:
                break
            finally:
                self.url_queue.task_done()

    async def fetch_url(self, session, url, retries) -> NetworkResult:
        '''
        Fetch a URL and return a NetworkResult object.
        '''
        try:
            headers = random.choice(self.headers_list)
            async with session.get(url, headers=headers, ssl=False) as response:
                # Limit response size to prevent memory issues
                if 'content-length' in response.headers:
                    content_length = int(response.headers['content-length'])
                    if content_length > self.MAX_RESPONSE_SIZE:
                        await self.report_status(url, "DEAD")
                        return NetworkResult(
                            url, 0, False, 
                            error_message=f"Response too large: {content_length} bytes",
                            attempts=retries
                        )
                
                # Read with size limit
                text = await response.text()
                if len(text) > self.MAX_RESPONSE_SIZE:
                    text = text[:self.MAX_RESPONSE_SIZE]  # Truncate if needed
                
                await self.report_status(url, "ALIVE")
                return NetworkResult(
                    url=url,
                    status=response.status,
                    success=True,
                    content=text,
                    headers=dict(response.headers),
                    content_type=response.headers.get('Content-Type'),
                    response_size=len(text),
                    attempts=retries
                )
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if retries < self.RETRY_LIMIT:
                await self.retry_queue.put((url, retries + 1))
                await self.report_status(url, f"RETRY {retries + 1}")
                return NetworkResult(url, 0, False, attempts=retries)
            else:
                await self.report_status(url, "DEAD")
                return NetworkResult(url, 0, False, error_message=str(e), attempts=retries)
        except Exception as e:
            await self.report_status(url, "DEAD")
            return NetworkResult(url, 0, False, error_message=str(e), attempts=retries)

    async def retry_worker(self):
        '''
        Retry a URL and put it back in the queue.
        '''
        while True:
            try:
                url, retries = await self.retry_queue.get()
                await asyncio.sleep(self.RETRY_DELAY)
                await self.url_queue.put((url, retries))
            except asyncio.CancelledError:
                break
            finally:
                self.retry_queue.task_done()

    async def processor_worker(self):
        '''
        Process a URL and put the result in the queue.
        '''
        loop = asyncio.get_running_loop()
        while True:
            try:
                net_result = await self.network_result_queue.get()
                if net_result.success and net_result.content is not None:
                    start = time.perf_counter()
                    processed_data = await loop.run_in_executor(
                        self.executor,
                        self.cpu_heavy_processing,
                        net_result.content,
                        net_result.url
                    )
                    processing_time = time.perf_counter() - start
                    
                    # Clear content from memory after processing
                    net_result = None  # Help GC
                    
                    processed = ProcessedResult(
                        net_result.url if net_result else "unknown",
                        net_result.status if net_result else 0,
                        True,
                        processed_data=processed_data,
                        processing_time=processing_time
                    )
                else:
                    processed = ProcessedResult(
                        net_result.url, 0, False,
                        error_message=net_result.error_message
                    )
                    net_result = None  # Help GC
                    
                await self.processed_result_queue.put(processed)
            except asyncio.CancelledError:
                break
            finally:
                self.network_result_queue.task_done()

    @staticmethod
    def cpu_heavy_processing(content: str, url: str) -> str:    
        '''
        Process a URL and return a string.
        '''
        count = content.lower().count("the")
        return f"Processed {url} ({count} occurrences of 'the')"

    async def writer_worker(self, output_file: str):
        '''
        Write the processed results to a file.
        '''
        async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
            while not (self.stop_event.is_set() and self.processed_result_queue.empty()):
                try:
                    result = await asyncio.wait_for(self.processed_result_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if result.success:
                    line = f"SUCCESS,{result.url},{result.status},\"{result.processed_data}\"\n"
                else:
                    line = f"FAILURE,{result.url},0,\"{result.error_message}\"\n"

                await f.write(line)
                await f.flush()
                self.processed_result_queue.task_done()

    async def report_status(self, url, status):
        '''
        Report the status of a URL.
        '''
        async with self.lock:
            if status == "ALIVE":
                self.stats['processed'] += 1
                self.stats['alive'] += 1
                print(f"{Colors.GREEN}[{self.stats['processed']}/{self.stats['total']}] {url} => Alive{Colors.ENDC}")
            elif status == "DEAD":
                self.stats['processed'] += 1
                self.stats['dead'] += 1
                print(f"{Colors.RED}[{self.stats['processed']}/{self.stats['total']}] {url} => Dead{Colors.ENDC}")
            elif "RETRY" in status:
                self.stats['retries'] += 1
                print(f"{Colors.YELLOW}{url} => {status}{Colors.ENDC}")

    async def run(self):
        '''
        Run the URLProcessor.
        '''
        await self.load_urls()

        if self.stats['total'] == 0:
            print(f"{Colors.RED}No URLs to process.{Colors.ENDC}")
            return

        # Initialize executor here for proper cleanup
        self.executor = ProcessPoolExecutor(max_workers=self.CPU_WORKERS)
        
        try:
            output_file = f"results_{self.filename}"
            connector = aiohttp.TCPConnector(limit=self.MAX_CONCURRENT_REQUESTS, ssl=False)
            timeout = aiohttp.ClientTimeout(total=60)

            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                writer_task = asyncio.create_task(self.writer_worker(output_file))

                fetchers = [
                    asyncio.create_task(self.fetch_worker(session))
                    for _ in range(self.MAX_CONCURRENT_REQUESTS)
                ]

                processors = [
                    asyncio.create_task(self.processor_worker())
                    for _ in range(self.executor._max_workers)
                ]

                retry_task = asyncio.create_task(self.retry_worker())

                try:
                    await self.url_queue.join()
                    await self.retry_queue.join()
                    await self.network_result_queue.join()
                    await self.processed_result_queue.join()
                finally:
                    self.stop_event.set()

                    # Cancel all tasks
                    for task in fetchers + processors:
                        task.cancel()
                    retry_task.cancel()

                    # Wait for cancellation with timeout
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*fetchers, *processors, retry_task, writer_task, return_exceptions=True),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        print("Warning: Some tasks didn't finish within timeout")

        finally:
            # Ensure executor is always cleaned up
            if self.executor:
                self.executor.shutdown(wait=True)
                self.executor = None

        print(f"\n{Colors.YELLOW}--- Completed ---{Colors.ENDC}")
        print(f"{Colors.WHITE}Total URLs: {self.stats['total']}{Colors.ENDC}")
        print(f"{Colors.GREEN}Alive: {self.stats['alive']}{Colors.ENDC}")
        print(f"{Colors.RED}Dead: {self.stats['dead']}{Colors.ENDC}")
        print(f"{Colors.YELLOW}Retries: {self.stats['retries']}{Colors.ENDC}")
        print(f"Results saved to: {Colors.WHITE}{output_file}{Colors.ENDC}")
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=False)


async def main():
    '''
    Main function with cross-platform support.
    '''
    # Set appropriate event loop policy based on platform
    if sys.platform == "win32":  # Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    elif sys.platform in ["linux", "darwin"]:  # Linux and macOS
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    elif sys.platform.startswith("freebsd"):  # FreeBSD
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    else:
        # For other Unix-like systems, try default policy
        print(f"Warning: Platform {sys.platform} not explicitly supported, using default event loop policy")
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

    filename = input("Enter the filename : ").strip()
    processor = URLProcessor(filename)
    await processor.run()


if __name__ == "__main__":
    asyncio.run(main())
