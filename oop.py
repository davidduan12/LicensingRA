import os, requests
import threading
from collections import defaultdict

from bs4 import BeautifulSoup
import time, re, lxml, cchardet, json
from datetime import datetime
import warnings
import urllib.parse
import logging
from logging import *
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)



log_path = 'sec.log'
logging.basicConfig(
    filename=log_path,
    encoding='utf-8',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
session = requests.Session()
session.headers.update({
    'User-Agent': 'D Duan d.duan@mail.utoronto.ca',
    'Accept-Encoding': "gzip, deflate",
    'Host': 'www.sec.gov',
})
# Base directory for saving files
BASE_DIR = os.getcwd()

# Valid form types
# VALID_FORMS = {'10-K', '10-Q', '8-K'}
VALID_FORMS = ['10-K']
# Keywords to search in exhibits
KEYWORDS = ['licensing', 'license agreement', 'sixth supplemental indenture']

# Directory
COMPANIES_DIR = './test_folder'

class BaseFormHandler:
    def __init__(self, cik, name):
        self.cik = cik
        self.company_name = name
        self.dir = os.path.join(BASE_DIR, name)
        os.makedirs(self.dir, exist_ok=True)

    @classmethod
    def process_filing(cls, name, cik, acc_num, date):
        pass

    @staticmethod
    def download_file(url, accession_folder, save_path):
        try:
            response = session.get(url)
            if response.status_code == 200:
                os.makedirs(accession_folder, exist_ok=True)
                with open(save_path, 'wb') as file:
                    file.write(response.content)
                logger.info(f"Downloaded file to {save_path}")
            else:
                logger.warning(f"Failed to download {url}")
        except Exception as e:
            logger.error(f"Error downloading file: {e}")

    @staticmethod
    def normalize_text(text: str) -> str:
        import unicodedata
        if text:
            text = re.sub(r'\s+', ' ', text)
            return text.replace(u'\u00A0', ' ').strip().lower()
        return ''

    @staticmethod
    def normalize_text_caps(text):
        if text:
            text = re.sub(r'\s+', ' ', text)
            return text.replace(u'\u00A0', ' ').strip()
        return ''

    @staticmethod
    def clean_exhibit_number(exhibit_number: str) -> str:
        import unicodedata
        import re
        # Normalize and remove unwanted characters
        exhibit_number = unicodedata.normalize('NFKD', exhibit_number)
        exhibit_number = re.sub(r'\s+', ' ', exhibit_number)
        exhibit_number = re.sub(r'[^a-zA-Z0-9.()-]', '', exhibit_number)
        return exhibit_number

    @staticmethod
    def has_keyword(self, cell, keywords: list[str]) -> bool:
        text = cell.get_text(strip=True)
        for keyword in keywords:
            if keyword in self.normalize_text(text):
                return True
        return False

    @staticmethod
    def fetch_page(url: str):
        try:
            start_time = time.time()
            response = session.get(url)
            print(response.headers.get('content-type'))
            end_time = time.time()
            logger.info(f"Request to {url} took {end_time - start_time:.2f} seconds")
            if response.status_code == 200:
                return BeautifulSoup(response.content, 'lxml')
            else:
                logger.warning(f"Failed to fetch page {url} (Status code: {response.status_code})")
        except Exception as e:
            logger.error(f"Exception occurred while fetching page {url}: {e}")
        return None

    @staticmethod
    def find_main_document_link(soup, form_type: str) -> str | None:
        table = soup.find('table', {'summary': 'Document Format Files'})
        if not table:
            logger.warning("No document table found on index page.")
            return None
        rows = table.find_all('tr')
        for row in rows:
            tds = row.find_all('td')
            if len(tds) >= 4 and form_type in tds[3].text:
                link_tag = tds[2].find('a', href=True)
                if link_tag:
                    document_link = link_tag['href']
                    logger.info(f"Found {form_type} document link: {document_link}")
                    return document_link
        logger.warning(f"No {form_type} document found.")
        return None

    @staticmethod
    def get_full_url(href):
        if href.startswith('http://') or href.startswith('https://'):
            return href  # Return as-is
        else:
            return f"https://www.sec.gov{href}"  # Relative URL, prefix with base SEC URL

    @staticmethod
    def xbrl_to_html(url):
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.path == '/ix':
            # Extract the 'doc' parameter from the query string
            query_params = urllib.parse.parse_qs(parsed_url.query)
            doc_path = query_params.get('doc', [None])[0]
            if doc_path:
                # Build the new URL without 'ix?doc='
                new_url = urllib.parse.urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    doc_path,
                    '', '', ''
                ))
            else:
                print("No 'doc' parameter found in the URL.")
        else:
            # If the URL doesn't start with '/ix', return it as is
            new_url = url
        return new_url

# Handler for 10-K forms
class TenKFormHandler(BaseFormHandler):
    @classmethod
    def process_filing(cls, name: str, cik: str, acc_number: str, date: str):
        self = cls(name=name, cik=cik)
        logger.info(f"Processing 10-K filing {acc_number} for {self.company_name}")

        index_url = self.get_index_url(acc_number)
        soup = self.fetch_page(index_url)
        if not soup:
            print("soup return ERROR")
            return

        filing_year = datetime.strptime(date, '%Y-%m-%d').year
        if not filing_year:
            return

        # Create directories
        accession_folder = self.dir_path(filing_year, '10-K', acc_number)

        # Find the main document link
        document_link = self.find_main_document_link(soup, '10-K')
        if not document_link:
            return
        document_link = self.xbrl_to_html(document_link)
        # Fetch and parse the main document
        full_doc_url = f"https://www.sec.gov{document_link}"
        doc_soup = self.fetch_page(full_doc_url)
        if not doc_soup:
            return
        print(full_doc_url)
        # Process exhibits
        logger.info(f'Starting process exhibits for {acc_number}')
        self.process_exhibits(doc_soup, accession_folder, soup)

    def get_index_url(self, accession_number: str) -> str:
        accession_number_nodashes = accession_number.replace('-', '')
        return (f'https://www.sec.gov/Archives/edgar/data/{self.cik}/'
                    f'{accession_number_nodashes}/{accession_number}-index.html')

    def dir_path(self, filing_year: int, form_type: str, accession_number: str) -> str:
        year_folder = os.path.join(self.dir, str(filing_year))
        form_folder = os.path.join(year_folder, form_type)
        accession_folder = os.path.join(form_folder, accession_number)
        return accession_folder

    def process_exhibits(self, doc_soup, accession_folder: str, soup):
        key = doc_soup.find_all(string=lambda t: t and 'part iv' in self.normalize_text(t))
        if not key:
            key = doc_soup.find_all(string=lambda t: t and 'ITEM 15' in self.normalize_text_caps(t))
        if not key:
            logger.warning("No 'Part IV' section found in the document.")
            return

        last_section = key[-1]
        exhibits = []

        for sibling in last_section.find_all_next():
            if sibling and sibling.name == 'table':
                rows = sibling.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        exhibit_number = cells[0].get_text(strip=True)
                        contain = [self.has_keyword(self, cell, KEYWORDS) for cell in cells[1:]]
                        if any(contain):
                            exhibit_number = self.clean_exhibit_number(exhibit_number)
                            logger.info(f"Found exhibit: {exhibit_number}")
                            link_tag = cells[0].find('a', href=True)
                            if not link_tag:
                                link_tag = cells[contain.index(True) + 1].find('a', href=True)
                            if link_tag and 'sec.gov' in link_tag['href']:
                                filing_url = link_tag['href']
                                save_path = os.path.join(accession_folder, f"{exhibit_number}.html")
                                self.download_file(filing_url, accession_folder, save_path)
                            else:
                                c = cells[1:]
                                exhibits.append((exhibit_number, c[contain.index(True)]))
        logger.info(exhibits)
        # Handle exhibits without direct links
        if exhibits:
            self.download_missing_exhibits(soup, exhibits, accession_folder)

    def download_missing_exhibits(self, soup, exhibits: list[tuple], accession_folder: str):
        table = soup.find('table', {'summary': 'Document Format Files'})
        rows = table.find_all('tr')
        for exhibit, description in exhibits:
            for row in rows:
                tds = row.find_all('td')
                if len(tds) >= 4 and 'EX-' in tds[3].text:
                    exhibit_tag = tds[3].text.strip()
                    if exhibit_tag[3:] == exhibit:
                        link_tag = tds[2].find('a', href=True)
                        if link_tag:
                            document_link = self.get_full_url(link_tag['href'])
                            path = os.path.join(accession_folder, f"{tds[3].text[3:]}.html")
                            print(f"Downloading file for {tds[3].text} from {document_link}")
                            logger.info(f"Downloading exhibit {exhibit} to {path} from {document_link}")
                            self.download_file(document_link, accession_folder, path)
                            exhibits.remove((exhibit, description))
                            break
                        else:
                            logger.warning(f"Link tag not found for {tds[3].text}")
        if exhibits:
            for exhibit, description in exhibits:
                os.makedirs(accession_folder, exist_ok=True)
                with open(os.path.join(accession_folder, "extras.txt"), "a", encoding='utf-8') as f:
                    print("exhibit:", exhibit)
                    f.write(exhibit + ":" + self.normalize_text(description.text) + "\n")
                    logger.info(f'Wrote to extras.txt')
                f.close()



class TenQFormHandler(BaseFormHandler):
    @classmethod
    def process_filing(cls, name: str, cik: str, acc_number: str, date: str):
        self = cls(name=name, cik=cik)
        logger.info(f"Processing 10-Q filing {acc_number} for {self.company_name}")
        index_url = self.get_index_url(acc_number)
        soup = self.fetch_page(index_url)
        if not soup:
            print("soup return ERROR")
            return

        filing_year = datetime.strptime(date, '%Y-%m-%d').year
        if not filing_year:
            return

        # Create directories
        accession_folder = self.dir_path(filing_year, '10-Q', acc_number)

        # Find the main document link
        document_link = self.find_main_document_link(soup, '10-Q')
        if not document_link:
            return
        document_link = self.xbrl_to_html(document_link)
        # Fetch and parse the main document
        full_doc_url = f"https://www.sec.gov{document_link}"
        doc_soup = self.fetch_page(full_doc_url)
        if not doc_soup:
            return
        print(full_doc_url)
        # Process exhibits
        logger.info(f'Starting process exhibits for {acc_number}')
        self.process_exhibits(doc_soup, accession_folder)

    def get_index_url(self, accession_number: str) -> str:
        accession_number_nodashes = accession_number.replace('-', '')
        return (f'https://www.sec.gov/Archives/edgar/data/{self.cik}/'
                    f'{accession_number_nodashes}/{accession_number}-index.html')

    def dir_path(self, filing_year: int, form_type: str, accession_number: str) -> str:
        year_folder = os.path.join(self.dir, str(filing_year))
        form_folder = os.path.join(year_folder, form_type)
        accession_folder = os.path.join(form_folder, accession_number)
        return accession_folder

    def process_exhibits(self, doc_soup, accession_folder: str):
        key = doc_soup.find_all(string=lambda t: t and 'item 6' in self.normalize_text(t))
        if not key:
            logger.warning("No 'Part IV' section found in the document.")
            return

        last_section = key[-1]
        exhibits = []

        for sibling in last_section.find_all_next():
            if sibling and sibling.name == 'table':
                rows = sibling.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        exhibit_number = cells[0].get_text(strip=True)
                        if any(self.has_keyword(cell, KEYWORDS) for cell in cells[1:]):
                            exhibit_number = self.clean_exhibit_number(exhibit_number)
                            logger.info(f"Found exhibit: {exhibit_number}")
                            link_tag = cells[0].find('a', href=True)
                            if link_tag and 'sec.gov' in link_tag['href']:
                                filing_url = link_tag['href']
                                save_path = os.path.join(accession_folder, f"{exhibit_number}.html")
                                self.download_file(filing_url, accession_folder, save_path)
                            else:
                                exhibits.append(exhibit_number)
        # Handle exhibits without direct links
        if exhibits:
            self.download_missing_exhibits(doc_soup, exhibits, accession_folder)

    def download_missing_exhibits(self, doc_soup, exhibits: list[str], accession_folder: str):
        table = doc_soup.find('table', {'summary': 'Document Format Files'})
        rows = table.find_all('tr')
        for exhibit in exhibits:
            for row in rows:
                tds = row.find_all('td')
                if len(tds) >= 4 and 'EX-' in tds[3].text:
                    exhibit_tag = tds[3].text.strip()
                    if exhibit_tag[3:] == exhibit:
                        link_tag = tds[2].find('a', href=True)
                        if link_tag:
                            document_link = self.get_full_url(link_tag['href'])
                            path = os.path.join(accession_folder, f"{tds[3].text}.html")
                            print(f"Downloading file for {tds[3].text} from {document_link}")
                            logger.info(f"Downloading exhibit {exhibit} to {path} from {document_link}")
                            self.download_file(document_link, accession_folder, path)

class EightKFormHandler(BaseFormHandler):
    @classmethod
    def process_filing(cls, name: str, cik: str, acc_number: str, date: str):
        self = cls(name=name, cik=cik)
        logger.info(f"Processing 8-K filing {acc_number} for {self.company_name}")
        index_url = self.get_index_url(acc_number)
        soup = self.fetch_page(index_url)
        if not soup:
            print("soup return ERROR")
            return

        filing_year = datetime.strptime(date, '%Y-%m-%d').year
        if not filing_year:
            return

        # Create directories
        accession_folder = self.dir_path(filing_year, '8-K', acc_number)

        # Find the main document link
        document_link = self.find_main_document_link(soup, '8-K')
        if not document_link:
            return
        document_link = self.xbrl_to_html(document_link)
        # Fetch and parse the main document
        full_doc_url = f"https://www.sec.gov{document_link}"
        doc_soup = self.fetch_page(full_doc_url)
        if not doc_soup:
            return
        print(full_doc_url)
        # Process exhibits
        logger.info(f'Starting process exhibits for {acc_number}')
        self.process_exhibits(doc_soup, accession_folder)

    def get_index_url(self, accession_number: str) -> str:
        accession_number_nodashes = accession_number.replace('-', '')
        return (f'https://www.sec.gov/Archives/edgar/data/{self.cik}/'
                    f'{accession_number_nodashes}/{accession_number}-index.html')

    def dir_path(self, filing_year: int, form_type: str, accession_number: str) -> str:
        year_folder = os.path.join(self.dir, str(filing_year))
        form_folder = os.path.join(year_folder, form_type)
        accession_folder = os.path.join(form_folder, accession_number)
        return accession_folder

    def process_exhibits(self, doc_soup, accession_folder: str):
        key = doc_soup.find_all(string=lambda t: t and 'item 9.01' in self.normalize_text(t))
        if not key:
            logger.warning("No 'item 9.01' section found in the document.")
            return

        last_section = key[-1]
        exhibits = []

        for sibling in last_section.find_all_next():
            if sibling and sibling.name == 'table':
                rows = sibling.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        exhibit_number = cells[0].get_text(strip=True)
                        if any(self.has_keyword(cell, KEYWORDS) for cell in cells[1:]):
                            exhibit_number = self.clean_exhibit_number(exhibit_number)
                            logger.info(f"Found exhibit: {exhibit_number}")
                            link_tag = cells[0].find('a', href=True)
                            if link_tag and 'sec.gov' in link_tag['href']:
                                filing_url = link_tag['href']
                                save_path = os.path.join(accession_folder, f"{exhibit_number}.html")
                                self.download_file(filing_url, accession_folder, save_path)
                            else:
                                exhibits.append(exhibit_number)
        # Handle exhibits without direct links
        if exhibits:
            self.download_missing_exhibits(doc_soup, exhibits, accession_folder)

    def download_missing_exhibits(self, doc_soup, exhibits: list[str], accession_folder: str):
        table = doc_soup.find('table', {'summary': 'Document Format Files'})
        rows = table.find_all('tr')
        for exhibit in exhibits:
            for row in rows:
                tds = row.find_all('td')
                if len(tds) >= 4 and 'EX-' in tds[3].text:
                    exhibit_tag = tds[3].text.strip()
                    if exhibit_tag[3:] == exhibit:
                        link_tag = tds[2].find('a', href=True)
                        if link_tag:
                            document_link = self.get_full_url(link_tag['href'])
                            path = os.path.join(accession_folder, f"{tds[3].text}.html")
                            print(f"Downloading file for {tds[3].text} from {document_link}")
                            logger.info(f"Downloading exhibit {exhibit} to {path} from {document_link}")
                            self.download_file(document_link, accession_folder, path)
# Factory class to get the appropriate form handler
class FormHandlerFactory:
    @staticmethod
    def get_form_handler(form_type: str):
        if form_type == '10-K':
            return TenKFormHandler
        elif form_type == '10-Q':
            return TenQFormHandler
        elif form_type == '8-K':
            return EightKFormHandler
        else:
            return None


# def process_company_file(json_file_path: str):
#     try:
#         with open(json_file_path, 'r') as f:
#             company_data = json.load(f)
#     except Exception as e:
#         logger.error(f"Failed to read company file {json_file_path}: {e}")
#         return
#
#     company_name = company_data.get('name', 'Unknown Company')
#     cik = company_data.get('cik', '').lstrip('0')  # Remove leading zeros
#     filings = company_data.get('filings', {}).get('recent', {})
#     accession_numbers = filings.get('accessionNumber', [])
#     forms = filings.get('form', [])
#     filing_date = filings.get('filingDate', {})
#
#     if not accession_numbers or not forms:
#         logger.warning(f"No filings found in {json_file_path}")
#         return
#
#     # Prepare a list of filings to process
#     filings_to_process = [
#         (acc_num, doc_type, date) for acc_num, doc_type, date in
#             zip(accession_numbers, forms, filing_date) if doc_type in VALID_FORMS
#     ]
#
#     if not filings_to_process:
#         logger.info(f"No valid filings to process for {company_name}")
#         return
#     print(len(filings_to_process))
#     # Process filings concurrently using threads
#     with ThreadPoolExecutor(max_workers=5) as executor:
#         futures = []
#         for acc_num, doc_type, date in filings_to_process:
#             handler_class = FormHandlerFactory.get_form_handler(doc_type)
#             if handler_class:
#                 future = executor.submit(
#                     handler_class.process_filing,
#                     company_name,
#                     cik,
#                     acc_num,
#                     date
#                 )
#                 futures.append(future)
#             else:
#                 logger.info(f"No handler for form type {doc_type}")
#
#         for future in as_completed(futures):
#             try:
#                 future.result()
#             except Exception as e:
#                 logger.error(f"Error processing filing: {e}")

def process_company_file(paths: list):
    filings_to_process = []
    company_name = None
    cik = -1
    for path in paths:
        match = re.match(r'CIK(\d+)\.json', path)
        if match:
            try:
                with open(os.path.join(COMPANIES_DIR, path), 'r') as f:
                    company_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read company file {path}: {e}")
                return
            company_name = company_data.get('name', 'Unknown Company')
            cik = company_data.get('cik', '').lstrip('0')  # Remove leading zeros
            filings = company_data.get('filings', {}).get('recent', {})
            paths.remove(path)
            accession_numbers = filings.get('accessionNumber', [])
            forms = filings.get('form', [])
            filing_dates = filings.get('filingDate', [])
            filings_to_process.extend([
                (acc_num, form_type, date) for acc_num, form_type, date in
                zip(accession_numbers, forms, filing_dates) if form_type in VALID_FORMS
            ])
            break
    for path in paths:
        try:
            with open(os.path.join('./test_folder', path), 'r') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read company file {path}: {e}")
            return
        accession_numbers = data.get('accessionNumber', [])
        forms = data.get('form', [])
        filing_dates = data.get('filingDate', [])
        filings_to_process.extend([
            (acc_num, form_type, date) for acc_num, form_type, date in
            zip(accession_numbers, forms, filing_dates) if form_type in VALID_FORMS
        ])
    if not filings_to_process:
        logger.info(f"No valid filings to process for {company_name}")
        return
    # Process filings sequentially
    for acc_num, form_type, date in filings_to_process:
        handler_class = FormHandlerFactory.get_form_handler(form_type)
        if handler_class:
            handler_class.process_filing(company_name, cik, acc_num, date)
        else:
            logger.info(f"No handler for form type {form_type}")


def main():
    # # Directory containing company JSON files
    start = time.time()
    logger.info(f"Started at {start}")

    # List all JSON files in the directory
    json_files = [
        f for f in os.listdir(COMPANIES_DIR) if f.endswith('.json')
    ]
    companies = defaultdict(list)
    for file in json_files:
        match = re.match(r'CIK(\d+)(?:-submissions.*)?\.json', file)
        if match:
            companies[match.group(1).lstrip('0')].append(file)
        else:
            logger.info(f'{file} does not match expected format')
    print(companies)
    for cik, files in companies.items():
        process_company_file(files)
    end = time.time()
    logger.info(f"Finished at {end}")
    logger.info(f"Time taken is {end - start}")
if __name__ == '__main__':
    main()