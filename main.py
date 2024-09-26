import requests
from bs4 import BeautifulSoup
import time, re
start = time.time()

#url = 'https://www.sec.gov/Archives/edgar/data/318306/000114420419014623/0001144204-19-014623-index.html'
url = 'https://www.sec.gov/Archives/edgar/data/1011006/000119312510043149/0001193125-10-043149-index.html'

# REQUIRED
headers = {
    'User-Agent': 'D Duan d.duan@mail.utoronto.ca',
    'Accept-Encoding': "gzip, deflate",
    'Host': 'www.sec.gov',
}
response = requests.get(url, headers=headers)
print(response.status_code)


# Get link to 10-k document
soup = BeautifulSoup(response.content, 'html.parser')
table = soup.find('table', {'summary': 'Document Format Files'})
rows = table.find_all('tr')

for row in rows:    # Loop through rows
    tds = row.find_all('td')
    if len(tds) >= 4 and '10-K' in tds[3].text:
        # Extract the href link from the third td
        link_tag = tds[2].find('a', href=True)
        if link_tag:
            document_link = link_tag['href']
            print(f"Found 10-K document link: {document_link}")


keywords = ['licensing', 'license agreement']
def has_keyword(cell, keywords):
    text = cell.get_text(strip=True)
    for keyword in keywords:
        if keyword in text.lower():
            return True
    return False

def download_file(url, exhibit_number):
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        file_name = f"{exhibit_number}.html"
        with open(file_name, 'wb') as file:
            file.write(response.content)
        print(f"Downloaded")
    else:
        print(f"Failed to download {url}")


def normalize_text(text):
    if text:
        # Replace &nbsp; with space
        return text.replace(u'\u00A0', ' ').strip().lower()
    return ''


# Fetch the actual 10-K document
full_doc_url = f"https://www.sec.gov{document_link}"
doc_response = requests.get(full_doc_url, headers=headers)
doc_soup = BeautifulSoup(doc_response.content, 'html.parser')

# Look for the PART IV symbol
part_iv = doc_soup.find_all(string=lambda t: t and 'part iv' in normalize_text(t))
exhibits = []   #   Set of exhibits waiting to be downloaded
if part_iv:
    last_one = part_iv[-1]  # Only need to look starting form the last one
    for sibling in last_one.find_all_next():
        if sibling and sibling.name == 'table': # Look for tables
            row1 = sibling.find_all('tr')

            for row in row1:
                cells = row.find_all('td')
                if len(cells) > 1:
                    exhibit_number = cells[0].get_text(strip=True)  # Column 1 is exhibit number
                    if any(has_keyword(cell, keywords) for cell in cells[1:]):  # Check keywords for all other columns
                        exhibit_number = re.sub(r'[*+†]', '', exhibit_number)
                        print(f"Exhibit Number: {exhibit_number}")
                        link_tag = cells[0].find('a', href=True)
                        if link_tag and 'sec.gov' in link_tag['href']:  # Download directly
                            filing_url = link_tag['href']
                            print(f"Downloading file for {exhibit_number} from {filing_url}")
                            download_file(filing_url, exhibit_number)
                        else:
                            exhibits.append(exhibit_number)  # Otherwise download from index.html page
print(exhibits)
def get_full_url(href):
    if href.startswith('http://') or href.startswith('https://'):
        return href  # Return as-is
    else:
        return f"https://www.sec.gov{href}"  # Relative URL, prefix with base SEC URL


for row in rows:    # Go back to original table and match exhibits to download
    tds = row.find_all('td')
    if len(tds) >= 4 and 'EX-' in tds[3].text and tds[3].text[3:] in exhibits:  # Using fourth element
        link_tag = tds[2].find('a', href=True)
        if link_tag:
            document_link = get_full_url(link_tag['href'])
            print(f"Downloading file for {tds[3].text} from {document_link}")
            download_file(document_link, tds[3].text[3:])
print(time.time() - start)

