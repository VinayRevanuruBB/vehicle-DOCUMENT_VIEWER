from flask import Flask, render_template, jsonify, request, send_file
import pandas as pd
import requests
from datetime import datetime, timedelta
import io
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory cache
memory_cache = {}
CACHE_DURATION = timedelta(minutes=30)  # Cache for 30 minutes

def get_year_range():
    """Get year range from current year to 1980"""
    current_year = datetime.now().year
    return list(range(current_year, 1980, -1))

def clean_filename(text):
    """Clean string for filename"""
    cleaned = re.sub(r'[^a-zA-Z0-9\s-]', '', text)
    cleaned = cleaned.replace(' ', '_')
    return cleaned

def get_cached_data(year):
    """Get data from memory cache if available and not expired"""
    if year in memory_cache:
        cached_time, data = memory_cache[year]
        if datetime.now() - cached_time < CACHE_DURATION:
            logger.info(f"Using cached data for year {year}")
            return data
        else:
            # Remove expired cache
            del memory_cache[year]
            logger.info(f"Cache expired for year {year}")
    return None

def cache_data(year, data):
    """Store data in memory cache"""
    memory_cache[year] = (datetime.now(), data)
    logger.info(f"Cached data for year {year}")

def fetch_nhtsa_data(year):
    """Fetch NHTSA data for a specific year with in-memory caching"""
    # Check cache first
    cached_data = get_cached_data(year)
    if cached_data is not None:
        return cached_data
    
    logger.info(f"Fetching data for year {year} from NHTSA API")
    
    all_data = pd.DataFrame()
    page = 1
    max_pages = 10  # Limit to prevent infinite loops
    
    while page <= max_pages:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetParts?type=565&fromDate=1/1/{year}&toDate=12/31/{year}&format=csv&page={page}"
        
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"API returned status code {response.status_code} for year {year}, page {page}")
                break
                
            df = pd.read_csv(io.StringIO(response.text))
            
            if df.empty or len(df) < 10:  # If we get very few results, we're probably at the end
                logger.info(f"Reached end of data for year {year} at page {page}")
                break
                
            all_data = pd.concat([all_data, df], ignore_index=True)
            page += 1
            
        except Exception as e:
            logger.error(f"Error fetching data for year {year}, page {page}: {str(e)}")
            break
    
    logger.info(f"Fetched {len(all_data)} records for year {year}")
    
    # Cache the data
    if not all_data.empty:
        cache_data(year, all_data)
    
    return all_data

@app.route('/')
def index():
    years = get_year_range()
    return render_template('index.html', years=years)

@app.route('/get_manufacturers/<int:year>')
def get_manufacturers(year):
    sort_by = request.args.get('sort', 'date')  # Default to date sorting
    logger.info(f"Getting manufacturers for year {year}, sorted by {sort_by}")
    
    # Fetch data in real-time
    data = fetch_nhtsa_data(year)
    
    if data.empty:
        return jsonify({
            'manufacturers': [],
            'error': f'No data found for year {year}'
        })
    
    if 'manufacturername' not in data.columns:
        return jsonify({
            'manufacturers': [],
            'error': 'Invalid data format received from API'
        })
    
    if sort_by == 'date' and 'letterdate' in data.columns:
        # Sort by most recent date
        manufacturer_dates = data.groupby('manufacturername')['letterdate'].max().reset_index()
        manufacturer_dates['letterdate'] = pd.to_datetime(manufacturer_dates['letterdate'], errors='coerce')
        manufacturer_dates = manufacturer_dates.sort_values('letterdate', ascending=False, na_position='last')
        
        # Include date information
        manufacturer_list = []
        for _, row in manufacturer_dates.iterrows():
            manufacturer_list.append({
                'name': row['manufacturername'],
                'latest_date': row['letterdate'].strftime('%Y-%m-%d') if pd.notna(row['letterdate']) else 'No date'
            })
        
        logger.info(f"Found {len(manufacturer_list)} manufacturers sorted by date for year {year}")
        return jsonify({'manufacturers': manufacturer_list, 'sorted_by': 'date'})
    else:
        # Sort by name (default)
        manufacturers = sorted([m for m in data['manufacturername'].unique() if m and str(m).strip()])
        logger.info(f"Found {len(manufacturers)} manufacturers sorted by name for year {year}")
        return jsonify({'manufacturers': manufacturers, 'sorted_by': 'name'})

@app.route('/get_versions/<int:year>', methods=['POST'])
def get_versions(year):
    manufacturers = request.json.get('manufacturers', [])
    if not manufacturers:
        return jsonify({'error': 'No manufacturers selected'})
    
    logger.info(f"Getting versions for year {year}, manufacturers: {manufacturers}")
    
    # Fetch data in real-time
    data = fetch_nhtsa_data(year)
    
    if data.empty:
        return jsonify({'error': f'No data available for year {year}'})
    
    # Filter data for selected manufacturers
    filtered_data = data[data['manufacturername'].isin(manufacturers)]
    
    if filtered_data.empty:
        return jsonify({'error': 'No versions found for selected manufacturers'})
    
    logger.info(f"Found {len(filtered_data)} records for selected manufacturers")
    
    # Get versions with dates and convert letterdate to datetime for proper sorting
    versions = filtered_data[['manufacturername', 'name', 'letterdate']].drop_duplicates(subset=['manufacturername', 'name']).copy()
    
    # Convert letterdate to datetime for proper sorting
    versions['letterdate_dt'] = pd.to_datetime(versions['letterdate'], errors='coerce')
    
    # Sort by datetime (most recent first), then by manufacturer name, then by version name
    versions = versions.sort_values(['letterdate_dt', 'manufacturername', 'name'], ascending=[False, True, True], na_position='last')
    
    # Format versions for display
    version_list = []
    for _, row in versions.iterrows():
        version_list.append({
            'manufacturer': row['manufacturername'],
            'name': row['name'],
            'date': row['letterdate'],
            'display': f"{row['manufacturername']} - {row['name']} ({row['letterdate']})"
        })
    
    logger.info(f"Returning {len(version_list)} versions to frontend")
    return jsonify({'versions': version_list})

@app.route('/get_pdf/<int:year>', methods=['GET', 'POST'])
def get_pdf(year):
    if request.method == 'GET':
        manufacturer = request.args.get('manufacturer')
        version = request.args.get('version')
    else:
        manufacturer = request.form.get('manufacturer')
        version = request.form.get('version')
    
    logger.info(f"PDF request - Year: {year}, Manufacturer: {manufacturer}, Version: {version}")
    
    if not manufacturer or not version:
        return jsonify({'error': 'Missing manufacturer or version'})
    
    # Fetch data in real-time
    nhtsa_data = fetch_nhtsa_data(year)
    
    if nhtsa_data.empty:
        return jsonify({'error': f'No data available for year {year}'})
    
    # Get the PDF URL - try exact match first
    version_data = nhtsa_data[
        (nhtsa_data['manufacturername'] == manufacturer) & 
        (nhtsa_data['name'] == version)
    ]
    
    logger.info(f"Exact match found: {len(version_data)} records")
    
    if version_data.empty:
        # Try case-insensitive match
        version_data = nhtsa_data[
            (nhtsa_data['manufacturername'].str.lower() == manufacturer.lower()) & 
            (nhtsa_data['name'].str.lower() == version.lower())
        ]
        logger.info(f"Case-insensitive match found: {len(version_data)} records")
    
    if version_data.empty:
        logger.error(f"No version found for manufacturer: {manufacturer}, version: {version}")
        return jsonify({'error': f'Version "{version}" not found for manufacturer "{manufacturer}"'})
    
    # Check if URL column exists
    if 'url' not in version_data.columns:
        logger.error(f"URL column not found. Available columns: {version_data.columns.tolist()}")
        return jsonify({'error': 'PDF URL not available in data'})
    
    pdf_url = version_data.iloc[0]['url']
    logger.info(f"PDF URL: {pdf_url}")
    
    try:
        response = requests.get(pdf_url, timeout=30)
        if response.status_code == 200:
            # Create descriptive filename
            clean_manufacturer = clean_filename(manufacturer)
            clean_version = clean_filename(version)
            filename = f"{year}_{clean_manufacturer}_{clean_version}.pdf"
            
            if request.method == 'GET':
                # For viewing
                return send_file(
                    io.BytesIO(response.content),
                    mimetype='application/pdf',
                    as_attachment=False,
                    download_name=filename
                )
            else:
                # For downloading
                return send_file(
                    io.BytesIO(response.content),
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name=filename
                )
        else:
            logger.error(f"PDF fetch failed with status code: {response.status_code}")
            return jsonify({'error': f'Could not fetch PDF. Status code: {response.status_code}'})
    except Exception as e:
        logger.error(f"Error accessing PDF: {str(e)}")
        return jsonify({'error': f'Error accessing PDF: {str(e)}'})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True) 