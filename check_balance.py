import aiohttp
import asyncio
import pandas as pd
import sys
from bs4 import BeautifulSoup
import logging
from decimal import Decimal, InvalidOperation
from tqdm import tqdm

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Semaphore to limit concurrent requests
MAX_CONCURRENT_REQUESTS = 10
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Function to get SATORI balance for a single address asynchronously
async def get_balance(session, address, retries=3):
    url = f"https://evr.cryptoscope.io/address/address.php?address={address}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    async with semaphore:
        for attempt in range(retries):
            try:
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        balance = extract_balance(html_content)
                        return address, balance
                    else:
                        await asyncio.sleep(1)  # Wait before retrying
            except asyncio.TimeoutError:
                if attempt == retries - 1:
                    return address, "Timeout Error"
            except Exception as e:
                if attempt == retries - 1:
                    return address, f"Error: {str(e)}"
        return address, "Failed after retries"

# Extract balance from the HTML page using BeautifulSoup
def extract_balance(page_text):
    soup = BeautifulSoup(page_text, 'html.parser')
    satori_balance = soup.find(string="SATORI")
    if satori_balance:
        balance_row = satori_balance.find_next('td')
        if balance_row:
            return balance_row.text.strip()
    return "No SATORI found"

# Async function to handle balance checking for all addresses
async def check_balances(addresses):
    async with aiohttp.ClientSession() as session:
        tasks = [get_balance(session, address) for address in addresses]
        results = []
        for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Fetching balances"):
            results.append(await f)
        return results

# Load the addresses from a txt file
def load_addresses(file_path):
    try:
        with open(file_path, 'r') as file:
            return [line.strip() for line in file.readlines()]
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        sys.exit(1)

# Function to summarize balances
def summarize_balances(results):
    total_balance = Decimal('0')
    valid_balance_count = 0
    no_satori_count = 0
    error_count = 0

    for _, balance in results:
        try:
            # Try to convert the balance to a Decimal
            balance_value = Decimal(balance.replace(',', ''))
            total_balance += balance_value
            valid_balance_count += 1
        except InvalidOperation:
            # If conversion fails, check for "No SATORI" or count as an error
            if balance == "No SATORI found":
                no_satori_count += 1
            else:
                error_count += 1

    return {
        "total_balance": total_balance,
        "valid_balance_count": valid_balance_count,
        "no_satori_count": no_satori_count,
        "error_count": error_count,
        "average_balance": total_balance / valid_balance_count if valid_balance_count > 0 else Decimal('0')
    }

# Main function to execute the balance check
def main():
    if len(sys.argv) != 2:
        print("Usage: python3 check_balance_async.py addresses.txt")
        sys.exit(1)

    file_path = sys.argv[1]
    addresses = load_addresses(file_path)

    # Use asyncio to run the check_balances coroutine
    try:
        results = asyncio.run(check_balances(addresses))
        # Create a DataFrame to hold the results
        df = pd.DataFrame(results, columns=["Address", "SATORI Balance"])
        # Save the result as a CSV file
        df.to_csv("satori_balances.csv", index=False)
        logging.info("Results saved to satori_balances.csv")

        # Summarize balances
        summary = summarize_balances(results)
        print("\nSummary:")
        print(f"Total SATORI Balance: {summary['total_balance']}")
        print(f"Number of addresses with valid balance: {summary['valid_balance_count']}")
        print(f"Number of addresses with 'No SATORI': {summary['no_satori_count']}")
        print(f"Number of errors: {summary['error_count']}")
        print(f"Average SATORI Balance: {summary['average_balance']:.2f}")

    except Exception as e:
        logging.error(f"Error running the balance check: {e}")

if __name__ == "__main__":
    main()