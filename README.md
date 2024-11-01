# SEC Filings Scraper


## Setup
```python
pip install -r requirements.txt
```
  
## Usage
- Within the oop.py file, you can adjust the following:
    - `HEADER`: information used to query SEC Edgar
    - `VALID_FORMS`: set of form types interested in  
    - `KEYWORDS`: set of keywords you want to search through, currently only look for exact matches
    - `COMPANIES_DIR`: directory of where input files are located

## Sample
Currently a sample input of four companies are tested, consisting of PFIZER, ABEONA THERAPEUTICS INC, Hyatt Hotel Corp, and MAKO Surgical Corp. Of which the sample output is within **standard_result**. Notice that no relavant filings were found for PFIZER
