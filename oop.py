import csv
import os
import requests
from collections import defaultdict

from bs4 import BeautifulSoup
import time
import re
import json
from datetime import datetime
import warnings
import urllib.parse
import logging
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

# logging setup
log_path = 'sec.log'
logging.basicConfig(
    filename=log_path,
    encoding='utf-8',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# api setup
session = requests.Session()
session.headers.update({
    'User-Agent': 'D Duan d.duan@mail.utoronto.ca',
    'Accept-Encoding': "gzip, deflate",
    'Host': 'www.sec.gov',
})
# Base directory for saving files
BASE_DIR = os.getcwd()

# Valid form types
VALID_FORMS = {'10-K', '10-Q', '8-K', 'S-1', 'S-1/A'}
# Keywords to search in exhibits
# VALID_FORMS = {'10-K'}
KEYWORDS = ['license', 'licensing', 'license agreement', 'lease', 'royalty', 'royalties', 'milestone payment',
            'supply agreement', 'patent transfer', 'trademark transfer', 'technology transfer']
# Directory
COMPANIES_DIR = './test_folder'


class BaseFormHandler:
    def __init__(self, cik, name):
        self.cik = cik
        self.company_name = name
        self.dir = os.path.join(BASE_DIR, name)
        os.makedirs(self.dir, exist_ok=True)

    @classmethod
    def process_filing(cls, name, cik, acc_number, date, form_type):
        """
            Processes an SEC filing by fetching the document index, parsing the main document, and processing exhibits.

            Args:
                name (str): Company name.
                cik (str): Central Index Key of the company.
                acc_number (str): Accession number of the filing.
                date (str): Filing date in '%Y-%m-%d' format.
                form_type (str): Type of SEC form.
        """
        self = cls(name=name, cik=cik)
        logger.info(f"Processing {form_type} filing {acc_number} for {self.company_name}")
        index_url = self.get_index_url(acc_number)
        soup = self.fetch_page(index_url)
        if not soup:
            logger.error("Soup return ERROR")
            return

        filing_year = datetime.strptime(date, '%Y-%m-%d').year
        if not filing_year:
            return
        # Create directories
        accession_folder = self.dir_path(filing_year, form_type, acc_number)

        # Find the main document link
        document_link = self.find_main_document_link(soup, form_type)
        if not document_link:
            return
        document_link = self.xbrl_to_html(document_link)
        # Fetch and parse the main document
        full_doc_url = f"https://www.sec.gov{document_link}"
        # logger.info(full_doc_url)
        doc_soup = self.fetch_page(full_doc_url)
        if not doc_soup:
            logger.error("Soup return ERROR")
            return
        # Process exhibits
        # logger.info(f'Starting process exhibits for {acc_number}')
        self.process_exhibits(doc_soup, accession_folder, soup)

    @staticmethod
    def download_file(url, accession_folder, save_path, description):
        """
            Downloads a file from a URL, saves it to the specified path, and logs the download details.

            Args:
                url (str): URL of the file to download.
                accession_folder (str): Directory to save the file.
                save_path (str): Path to save the downloaded file.
                description (str): Description of the file being downloaded.
        """
        # Parse metadata
        parts = save_path.split(os.sep)
        name = parts[-5]
        year = parts[-4]
        doc_type = parts[-3]
        acc_number = parts[-2]
        exhibit_num = os.path.splitext(parts[-1])[0]

        # Attempt to download the file
        try:
            response = session.get(url)
            if response.status_code == 200:
                os.makedirs(accession_folder, exist_ok=True)
                with open(save_path, 'wb') as file:
                    file.write(response.content)
                logger.info(f"Downloaded file to {save_path}")
                print(f"Downloading file to {save_path}")

                # Save the description of the exhibit
                with open('exhibits_log.csv', mode='a', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)
                    writer.writerow(
                        [name, year, doc_type, acc_number, exhibit_num, description])
            else:
                logger.warning(f"Failed to download {url}")
        except Exception as e:
            logger.error(f"Error downloading file: {e}")

    @staticmethod
    def normalize_text(text: str) -> str:
        """
            Normalizes and cleans text by removing excess whitespace, replacing non-breaking spaces, and converting to lowercase.

            Args:
                text (str): Text to be normalized.

            Returns:
                str: Normalized text.
        """
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
        """
            Cleans exhibit number by normalizing characters, removing unwanted characters, and
            retaining alphanumeric parts.

            Args:
                exhibit_number (str): Exhibit number to clean.

            Returns:
                str: Cleaned exhibit number.
            """
        import unicodedata
        import re
        # Normalize and remove unwanted characters
        exhibit_number.replace(u'\u00A0', ' ')
        exhibit_number = unicodedata.normalize('NFKD', exhibit_number)
        exhibit_number = re.sub(r'\s+', ' ', exhibit_number)
        exhibit_number = re.sub(r'[^a-zA-Z0-9.-]', '', exhibit_number)
        return exhibit_number

    @staticmethod
    def has_keyword(self, cell, keywords: list[str]) -> bool:
        """
            Checks if a cell's text contains any specified keywords.

            Args:
                cell: HTML element to check for keywords.
                keywords (list[str]): List of keywords to search in cell text.

            Returns:
                bool: True if any keyword is found in the cell text, False otherwise.
        """
        text = self.normalize_text(cell.get_text(strip=True))
        for keyword in keywords:
            if re.search(rf'\b{re.escape(keyword)}\b', text):
                return True
        return False

    @staticmethod
    def fetch_page(url: str):
        """
            Fetches an HTML page and returns its BeautifulSoup object if successful.

            Args:
                url (str): URL of the page to fetch.

            Returns:
                BeautifulSoup | None: Parsed page content or None if fetching fails.
        """
        try:
            # start_time = time.time()
            response = session.get(url)
            # end_time = time.time()
            # logger.info(f"Request to {url} took {end_time - start_time:.2f} seconds")
            if response.status_code == 200:
                return BeautifulSoup(response.content, 'lxml')
            else:
                logger.warning(f"Failed to fetch page {url} (Status code: {response.status_code})")
        except Exception as e:
            logger.error(f"Exception occurred while fetching page {url}: {e}")
        return None

    @staticmethod
    def find_main_document_link(soup, form_type: str) -> str | None:
        """
            Finds the main document link of a specified form type in an SEC index page.

            Args:
                soup (BeautifulSoup): Parsed HTML content of the index page.
                form_type (str): Type of form to find.

            Returns:
                str | None: Link to the main document, or None if not found.
        """
        table = soup.find('table', {'summary': 'Document Format Files'})
        if not table:
            logger.warning("No document table found on index page.")
            return None
        rows = table.find_all('tr')

        # Iterate through every row and check the fourth column for corresponding type
        for row in rows:
            tds = row.find_all('td')
            if len(tds) >= 4 and form_type in tds[3].text:
                link_tag = tds[2].find('a', href=True)
                if link_tag:
                    document_link = link_tag['href']
                    # logger.info(f"Found {form_type} document link: {document_link}")
                    return document_link
        logger.warning(f"No {form_type} document found.")
        return None

    @staticmethod
    def get_full_url(href):
        """
            Converts a relative URL to a full SEC URL if needed.

            Args:
                href (str): Relative or full URL.

            Returns:
                str: Full SEC URL if relative, otherwise the original URL.
        """
        if href.startswith('http://') or href.startswith('https://'):
            return href  # Return as-is
        else:
            return f"https://www.sec.gov{href}"  # Relative URL, prefix with base SEC URL

    @staticmethod
    def xbrl_to_html(url):
        """
           Converts an XBRL URL to an HTML URL format for SEC filings.

           Args:
               url (str): Original XBRL URL.

           Returns:
               str: Converted HTML URL.
       """
        new_url = url
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
        return new_url

    def download_missing_exhibits(self, soup, exhibits: list[tuple], accession_folder: str):
        """
           Downloads any exhibits that don't have direct links within the filings.

           Args:
               soup (BeautifulSoup): Parsed HTML content of the document page.
               exhibits (list[tuple]): List of exhibits to check and download.
               accession_folder (str): Directory to save downloaded exhibits.
       """
        # Locate all tables
        table = soup.find('table', {'summary': 'Document Format Files'})
        rows = table.find_all('tr')
        copy = exhibits.copy()

        # Loop through rows and remove from set of leftover exhibits if found
        for exhibit, description in copy:
            for row in rows:
                tds = row.find_all('td')
                if len(tds) >= 4 and 'EX-' in tds[3].text:
                    exhibit_tag = tds[3].text.strip()
                    if exhibit_tag[3:] == exhibit.strip():
                        link_tag = tds[2].find('a', href=True)
                        if link_tag:
                            document_link = self.get_full_url(link_tag['href'])
                            path = os.path.join(accession_folder, f"{tds[3].text[3:]}.html")
                            # print(f"Downloading file for {tds[3].text} from {document_link}")
                            # logger.info(f"Downloading exhibit {exhibit} to {path} from {document_link}")
                            self.download_file(document_link, accession_folder, path, description.text)
                            exhibits.remove((exhibit, description))
                            break
                        else:
                            logger.warning(f"Link tag not found for {tds[3].text}")

        # For all exhibits without a link, log it to file
        if exhibits:
            for exhibit, description in exhibits:
                os.makedirs(accession_folder, exist_ok=True)
                with open(os.path.join(accession_folder, "extras.txt"), "a", encoding='utf-8') as f:
                    logger.info(exhibit)
                    # print("exhibit:", exhibit)
                    f.write(exhibit + ":" + self.normalize_text(description.text) + "\n")
                f.close()

    def get_index_url(self, accession_number: str) -> str:
        """
            Constructs the SEC index URL for a given accession number.

            Args:
                accession_number (str): Accession number of the filing.

            Returns:
                str: URL of the SEC filing index page.
        """
        accession_number_nodashes = accession_number.replace('-', '')
        return (f'https://www.sec.gov/Archives/edgar/data/{self.cik}/'
                f'{accession_number_nodashes}/{accession_number}-index.html')

    def dir_path(self, filing_year: int, form_type: str, accession_number: str) -> str:
        """
            Creates the directory path for filing storage based on year, form type, and accession number.

            Args:
                filing_year (int): Year of the filing.
                form_type (str): Type of SEC form.
                accession_number (str): Accession number of the filing.

            Returns:
                accession_folder: Full directory path for filing storage.
        """
        year_folder = os.path.join(self.dir, str(filing_year))
        form_folder = os.path.join(year_folder, form_type.replace('/', '_'))
        accession_folder = os.path.join(form_folder, accession_number)
        return accession_folder

    def process_tables(self, accession_folder, last_section):
        """
            Processes tables to find exhibits in SEC filings, identifying exhibit numbers and downloading files
            directly if available.

            Args:
                accession_folder (str): Directory to save exhibits.
                last_section: Last HTML section element to parse tables from.

            Returns:
                exhibits: List of leftover exhibits and descriptions for further processing.
        """
        exhibits = []
        viewed = set()
        # Traverse tables after the last section to find exhibits
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
                            # Ensure exhibit number is not empty
                            i = 1
                            while exhibit_number.strip() == "":
                                exhibit_number = exhibit_number + cells[i].get_text()
                                i += 1
                            exhibit_number = self.clean_exhibit_number(exhibit_number)
                            if not any(char.isdigit() for char in exhibit_number):
                                continue
                            # logger.info(f"Found exhibit: {exhibit_number}")

                            # Locate and download link if present, or append to exhibits for later
                            link_tag = cells[0].find('a', href=True)
                            if not link_tag:
                                link_tag = cells[contain.index(True) + 1].find('a', href=True)
                            if link_tag and 'sec.gov' in link_tag['href']:
                                filing_url = link_tag['href']
                                save_path = os.path.join(accession_folder, f"{exhibit_number}.html")
                                self.download_file(filing_url, accession_folder, save_path,
                                                   cells[1:][contain.index(True)].get_text(strip=True))
                            else:
                                c = cells[1:]
                                if c[contain.index(True)].get_text(strip=True) not in viewed:
                                    exhibits.append((exhibit_number, c[contain.index(True)]))
                                    viewed.add(c[contain.index(True)].get_text(strip=True))

        return exhibits

    def process_exhibits(self, doc_soup, accession_folder, soup):
        pass


class TenKFormHandler(BaseFormHandler):
    def process_exhibits(self, doc_soup, accession_folder: str, soup):
        key = doc_soup.find_all(
            string=lambda t: t and re.search(r'I\s*T\s*E\s*M\s*1\s*5', self.normalize_text_caps(t)))
        if not key:
            key = doc_soup.find_all(string=lambda t: t and 'part iv' in self.normalize_text(t))
        if not key:
            logger.warning("No corresponding section found in the document.")
            return

        last_section = key[-1]

        exhibits = self.process_tables(accession_folder, last_section)

        # logger.info(exhibits)

        if exhibits:    # Handle exhibits without direct links
            self.download_missing_exhibits(soup, exhibits, accession_folder)


class TenQFormHandler(BaseFormHandler):
    def process_exhibits(self, doc_soup, accession_folder: str, soup):
        key = doc_soup.find_all(
            string=lambda t: t and re.search(r'\bi\s*t\s*e\s*m\s*6\b', self.normalize_text(t), re.IGNORECASE))
        if not key:
            key = doc_soup.find_all(string=lambda t: t and 'part ii' in self.normalize_text(t))
        if not key:
            logger.warning("No corresponding sections found in the document.")
            return

        last_section = key[-1]
        exhibits = self.process_tables(accession_folder, last_section)
        if exhibits:    # Handle exhibits without direct links
            self.download_missing_exhibits(soup, exhibits, accession_folder)


class EightKFormHandler(BaseFormHandler):
    def process_exhibits(self, doc_soup, accession_folder: str, soup):
        key = doc_soup.find_all(
            string=lambda t: t and re.search(r'\bi\s*t\s*e\s*m\s*9\s*.\s*0\s*1\b', self.normalize_text(t), re.IGNORECASE))
        if not key:
            logger.warning("No 'item 9.01' section found in the document.")
            return

        last_section = key[-1]
        exhibits = self.process_tables(accession_folder, last_section)
        # logger.info(exhibits)
        # Handle exhibits without direct links
        if exhibits:
            self.download_missing_exhibits(soup, exhibits, accession_folder)


class S1FormHandler(BaseFormHandler):
    def process_exhibits(self, doc_soup, accession_folder: str, soup):
        key = doc_soup.find_all(
            string=lambda t: t and re.search(r'\bi\s*t\s*e\s*m\s*1\s*6\b', self.normalize_text(t), re.IGNORECASE))
        if not key:
            key = doc_soup.find_all(string=lambda t: t and 'part ii' in self.normalize_text_caps(t))
        if not key:
            logger.warning("No corresponding section found in S-1 document.")
            return

        last_section = key[-1]
        exhibits = self.process_tables(accession_folder, last_section)
        # logger.info(exhibits)
        # Handle exhibits without direct links
        if exhibits:
            self.download_missing_exhibits(soup, exhibits, accession_folder)


class S1AFormHandler(BaseFormHandler):
    def process_exhibits(self, doc_soup, accession_folder: str, soup):
        key = doc_soup.find_all(
            string=lambda t: t and re.search(r'\bi\s*t\s*e\s*m\s*1\s*6\b', self.normalize_text(t), re.IGNORECASE))
        if not key:
            key = doc_soup.find_all(string=lambda t: t and 'part ii' in self.normalize_text_caps(t))
        if not key:
            logger.warning("No corresponding section found in S-1/A document.")
            return

        last_section = key[-1]
        exhibits = self.process_tables(accession_folder, last_section)
        # logger.info(exhibits)
        # Handle exhibits without direct links
        if exhibits:
            self.download_missing_exhibits(soup, exhibits, accession_folder)


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
        elif form_type == 'S-1':
            return S1FormHandler
        elif form_type == 'S-1/A':
            return S1AFormHandler
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
    """
        Processes company filing data from JSON files, extracting relevant filings to process.

        Args:
            paths (list): List of paths to company JSON files.
    """
    filings_to_process = []
    company_name = None
    cik = -1

    # Loop over the list of paths, processing each company file
    for path in paths:
        match = re.match(r'CIK(\d+)\.json', path)
        if match:
            try:
                with open(os.path.join(COMPANIES_DIR, path), 'r') as f:
                    company_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read company file {path}: {e}")
                return

            # Retrieve company name and CIK
            company_name = company_data.get('name', 'Unknown Company')
            cik = company_data.get('cik', '').lstrip('0')  # Remove leading zeros

            # Retrieve recent filings and filter by valid forms
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

    # Process any remaining JSON files in paths (in the format of CIK##########-submissions-###.json)
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
            handler_class.process_filing(company_name, cik, acc_num, date, form_type)
        else:
            logger.info(f"No handler for form type {form_type}")


def main():
    start = time.time()
    logger.info(f"Started at {start}")

    # List all JSON files in the directory
    json_files = [
        f for f in os.listdir(COMPANIES_DIR) if f.endswith('.json')
    ]
    # json_files = ['CIK0001411861.json']

    # Group files by CIK to allow multi-file processing for each company
    companies = defaultdict(list)
    for file in json_files:
        match = re.match(r'CIK(\d+)(?:-submissions.*)?\.json', file)
        if match:
            companies[match.group(1).lstrip('0')].append(file)
        else:
            logger.info(f'{file} does not match expected format')

    # Process filings for each company based on grouped files
    for cik, files in companies.items():
        process_company_file(files)
    end = time.time()
    logger.info(f"Finished at {end}")
    logger.info(f"Time taken is {end - start}")
if __name__ == '__main__':
    main()