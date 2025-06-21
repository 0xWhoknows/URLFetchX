# URLFetchX: High-Performance Async URL Processor

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**URLFetchX** is a robust, high-performance Python script for concurrently fetching, processing, and saving data from a large list of URLs. It's built with modern asynchronous libraries (`asyncio`, `aiohttp`) and utilizes parallel processing for CPU-bound tasks.

## Core Features

* **High Concurrency**: Utilizes `asyncio` and `aiohttp` to handle hundreds of network requests simultaneously.
* **Parallel CPU Processing**: Leverages `concurrent.futures.ProcessPoolExecutor` to run CPU-intensive tasks on all available cores without blocking network I/O.
* **Robust Error Handling**: Automatically retries failed requests with configurable limits and delays.
* **Resource Management**: Implements backpressure to prevent the request queue from growing too large and consuming excess memory.
* **Detailed Reporting**: Provides real-time, color-coded console output of the status of each URL (Alive, Dead, Retry).
* **Structured Output**: Saves processed results and failures cleanly to a CSV file.

## How It Works

The script follows a pipeline architecture, decoupling the various stages of work for maximum efficiency.

`[Input File] -> https://www.merriam-webster.com/dictionary/queue -> [Fetch Workers] -> [Network Result Queue] -> [CPU Process Workers] -> [Processed Result Queue] -> [Writer Worker] -> [Output CSV]`

1.  **Load**: URLs are loaded from the input file into an initial queue.
2.  **Fetch**: Asynchronous workers pick URLs from the queue, fetch their content over the network, and place the results (or failures) into a network results queue.
3.  **Process**: A pool of parallel processes picks successful network results, performs a CPU-heavy data processing task on the content, and places the final result into a processed results queue.
4.  **Write**: A single asynchronous writer takes final results and writes them row-by-row to the output CSV file.

## Prerequisites

* Python 3.8 or newer
* `pip` for installing packages

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/0xWhoknows/URLFetchX.git
    cd URLFetchX
    ```

2.  **Install the required packages:**
    (Make sure you have a `requirements.txt` file in your project)
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Create your URL list:**
    Create a text file (e.g., `urls.txt`) and populate it with the URLs you want to process, one URL per line.

    ```
    [https://example.com](https://example.com)
    [https://www.python.org](https://www.python.org)
    [https://httpbin.org/status/404](https://httpbin.org/status/404)
    ```

2.  **Run the script:**
    Execute `urlfetchx.py` from your terminal.

    ```bash
    python urlfetchx.py
    ```

3.  **Provide the input file:**
    The script will prompt you to enter the name of your URL file.

    ```
    Enter input filename: urls.txt
    ```

4.  **Check the results:**
    The script will process all URLs and save the output in a new file named `results_<your_input_file>`. In this example, it would be `results_urls.txt`.

## Customization

The power of URLFetchX comes from its customizable processing logic.

### Modifying the Processing Logic

The main part to edit is the `cpu_heavy_processing` static method within the `URLProcessor` class. This is where you can add your own code to parse HTML, extract data, run computations, etc.

**Example:** To parse the HTML content and extract the page title using `BeautifulSoup`, you would:

1.  **Install the new library:**
    ```bash
    pip install beautifulsoup4
    ```
    (And remember to add `beautifulsoup4` to your `requirements.txt` file!)

2.  **Update the `cpu_heavy_processing` method:**

    ```python
    from bs4 import BeautifulSoup

    # Inside the URLProcessor class...
    @staticmethod
    def cpu_heavy_processing(content: str, url: str) -> str:
        """
        Parses the HTML content to extract the <title> tag.
        """
        try:
            soup = BeautifulSoup(content, 'html.parser')
            title = soup.title.string.strip() if soup.title else "No Title Found"
            return f"Title: {title}"
        except Exception as e:
            return f"Error processing HTML at {url}: {e}"
    ```

### Adjusting Configuration

You can tweak the script's performance by changing the class variables at the top of the `URLProcessor` class in `urlfetchx.py`:

* `MAX_CONCURRENT_REQUESTS`: Number of URLs to fetch at the same time.
* `CPU_WORKERS`: Number of CPU cores to use for processing. `None` auto-detects all available cores.
* `RETRY_LIMIT`: How many times to retry a failed URL.
* `RETRY_DELAY`: Seconds to wait before putting a failed URL back in the queue.
* `BACKPRESSURE_THRESHOLD`: The script will pause fetching new URLs if the queue of unprocessed items grows larger than this number.

