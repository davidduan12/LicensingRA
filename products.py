import csv

# Specify the path to your CSV file
csv_file_path = 'products_dataset.csv'
csv_path = 'output.csv'
# Open and read the CSV file
with open(csv_path, newline='',encoding="ISO-8859-1") as csvfile:
    reader = csv.DictReader(csvfile)

    # Extract unique company names
    unique_companies = set()
    for row in reader:
        unique_companies.add(row['Company.Name'])

    # Count the unique companies
    unique_company_count = len(unique_companies)

# Output the result
print(f'There are {unique_company_count} unique companies.')