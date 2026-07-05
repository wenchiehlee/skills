import os
import sys
import urllib3
from urllib.parse import urlparse
from io import BytesIO
import importlib.util, importlib.machinery
# Dynamically load self_update if present in same directory
self_update_path = Path(__file__).with_name('self_update.py')
if self_update_path.is_file():
    import importlib
    spec = importlib.util.spec_from_file_location('self_update', self_update_path)
    self_update = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(self_update)


# Ensure dependencies are installed
try:
    import requests
    from PIL import Image
except ImportError:
    import subprocess
    print("Installing missing dependencies (requests, pillow)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "pillow"])
    import requests
    from PIL import Image

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_company_domain(stock_id):
    """
    Query TWSE, TPEx, or ConceptStocks to get company domain by stock ID or US Ticker.
    """
    stock_id_upper = str(stock_id).strip().upper()

    # Pre-defined mapping for ConceptStocks (US Tech Giants)
    concept_stocks_domains = {
        "TSM": "tsmc.com",
        "NVDA": "nvidia.com",
        "AVGO": "broadcom.com",
        "GOOGL": "google.com",
        "GOOG": "google.com",
        "AMZN": "amazon.com",
        "META": "meta.com",
        "MSFT": "microsoft.com",
        "AMD": "amd.com",
        "AAPL": "apple.com",
        "ORCL": "oracle.com",
        "MU": "micron.com",
        "SNDK": "sandisk.com",
        "QCOM": "qualcomm.com",
        "LNVGY": "lenovo.com",
        "DELL": "dell.com",
        "HPQ": "hp.com",
        "HPE": "hpe.com",
        "INTC": "intel.com",
        "ASML": "asml.com",
        "ARM": "arm.com",
        "OPENAI": "openai.com"
    }

    if stock_id_upper in concept_stocks_domains:
        domain = concept_stocks_domains[stock_id_upper]
        print(f"Found ConceptStock (US Ticker) record for {stock_id_upper}. Domain: {domain}")
        return f"http://{domain}"

    # Check dynamically in ConceptStocks metadata CSV
    metadata_csv = r"C:\\Users\\WJLEE\\SynologyDrive\\NAS\\github.com\\biztrends.TW\\data\\ConceptStocks\\raw_conceptstock_company_metadata.csv"
    if os.path.exists(metadata_csv):
        try:
            import csv
            with open(metadata_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ticker = row.get("Ticker", "").strip().upper()
                    if ticker == stock_id_upper:
                        domain = f"{ticker.lower()}.com"
                        print(f"Found dynamic Ticker in ConceptStocks metadata: {ticker}. Guessing domain: {domain}")
                        return f"http://{domain}"
        except Exception as e:
            print(f"Warning: Failed to parse ConceptStocks metadata CSV: {e}", file=sys.stderr)

    print(f"Searching for stock ID: {stock_id}...")

    # 1. Check TWSE (Listed Companies)
    twse_url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    try:
        print("Checking TWSE (Listed Companies)...")
        r = requests.get(twse_url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data:
                company_code = str(item.get("公司代號", item.get("Code", item.get("\ufeff公司代號", "")))).strip()
                if company_code == str(stock_id):
                    url = item.get("網址", "").strip()
                    if url:
                        print(f"Found TWSE record for {stock_id}. Website: {url}")
                        return url
    except Exception as e:
        print(f"Warning: Failed to check TWSE API: {e}", file=sys.stderr)

    # 2. Check TPEx (OTC Companies)
    tpex_url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    try:
        print("Checking TPEx (OTC Companies)...")
        r = requests.get(tpex_url, verify=False, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data:
                company_code = str(item.get("SecuritiesCompanyCode", "")).strip()
                if company_code == str(stock_id):
                    url = item.get("WebAddress", "").strip()
                    if url:
                        print(f"Found TPEx record for {stock_id}. Website: {url}")
                        return url
    except Exception as e:
        print(f"Warning: Failed to check TPEx API: {e}", file=sys.stderr)

    # 3. Check TPEx (Emerging Companies - 興櫃)
    tpex_emerging_url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R"
    try:
        print("Checking TPEx (Emerging Companies)...")
        r = requests.get(tpex_emerging_url, verify=False, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data:
                company_code = str(item.get("SecuritiesCompanyCode", "")).strip()
                if company_code == str(stock_id):
                    url = item.get("WebAddress", "").strip()
                    if url:
                        print(f"Found TPEx Emerging record for {stock_id}. Website: {url}")
                        return url
    except Exception as e:
        print(f"Warning: Failed to check TPEx Emerging API: {e}", file=sys.stderr)

    print(f"Error: Stock ID {stock_id} not found in public company registries or ConceptStocks.", file=sys.stderr)
    return None

def extract_domain(url):
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "http://" + url
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.strip()
        if domain.startswith("www."):
            domain = domain[4:]
        domain = domain.split('/')[0].strip()
        return domain
    except Exception as e:
        print(f"Error parsing URL: {e}", file=sys.stderr)
        return None

def download_logo(domain, output_path, target_size=256):
    print(f"\nAttempting to download logo for domain: {domain}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    logo_data = None
    # Method 1: Hunter.io Company Logo API
    hunter_url = f"https://logos.hunter.io/{domain}"
    try:
        print(f"Calling Hunter.io API: {hunter_url}")
        r = requests.get(hunter_url, headers=headers, timeout=10)
        if r.status_code == 200 and len(r.content) > 500:
            logo_data = r.content
            print("Successfully fetched logo from Hunter.io")
    except Exception as e:
        print(f"Hunter.io API failed: {e}", file=sys.stderr)
    # Method 2: Google Favicon API (Fallback)
    if not logo_data:
        google_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=256"
        try:
            print(f"Falling back to Google Favicon API: {google_url}")
            r = requests.get(google_url, headers=headers, timeout=10)
            if r.status_code == 200:
                logo_data = r.content
                print("Successfully fetched favicon from Google")
        except Exception as e:
            print(f"Google Favicon API failed: {e}", file=sys.stderr)
    if not logo_data:
        print("Error: Could not retrieve logo from any provider.", file=sys.stderr)
        return False
    # Process Image with Pillow
    try:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        img = Image.open(BytesIO(logo_data))
        img = img.convert("RGBA")
        # Scale proportionally to target_size
        width, height = img.size
        if width > 0 and height > 0:
            aspect_ratio = width / height
            if width > height:
                new_width = target_size
                new_height = max(1, int(target_size / aspect_ratio))
            else:
                new_height = target_size
                new_width = max(1, int(target_size * aspect_ratio))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            # Apply rounded corners
            try:
                from PIL import ImageDraw, ImageChops
                mask = Image.new("L", img.size, 0)
                draw = ImageDraw.Draw(mask)
                radius = max(1, int(min(img.size) * 0.1))
                draw.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
                r_ch, g_ch, b_ch, a_ch = img.split()
                new_a = ImageChops.darker(a_ch, mask)
                img = Image.merge("RGBA", (r_ch, g_ch, b_ch, new_a))
            except Exception as e:
                print(f"Warning: Failed to apply rounded corners: {e}", file=sys.stderr)
        canvas = Image.new("RGBA", (target_size, target_size), (255, 255, 255, 0))
        offset_x = (target_size - img.width) // 2
        offset_y = (target_size - img.height) // 2
        canvas.paste(img, (offset_x, offset_y), img)
        canvas.save(output_path, "PNG")
        print(f"Saved: {os.path.abspath(output_path)} (Size: {target_size}x{target_size})")
        return True
    except Exception as e:
        print(f"Error processing/saving image: {e}", file=sys.stderr)
        return False

def main():
    if len(sys.argv) < 3:
        print("Usage: python <SKILL_DIR>/scripts/download_logo.py <StockID> <Output_Path> [Target_Size]", file=sys.stderr)
        print("Example: python download_logo.py 2357 ./asus.png 256", file=sys.stderr)
        sys.exit(1)
    stock_id = sys.argv[1].strip()
    output_path = sys.argv[2].strip()
    target_size = int(sys.argv[3]) if len(sys.argv) > 3 else 256
    url = get_company_domain(stock_id)
    if not url:
        sys.exit(1)
    domain = extract_domain(url)
    if not domain:
        print("Error: Could not extract valid domain from company website URL.", file=sys.stderr)
        sys.exit(1)
    success = download_logo(domain, output_path, target_size)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
