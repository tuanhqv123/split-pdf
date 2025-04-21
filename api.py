from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import uuid
import os
import tempfile
import shutil
import io
import PyPDF2
import requests
import gdown
from urllib.parse import urlparse
import time
from dotenv import load_dotenv

# Nạp các biến môi trường từ file .env
load_dotenv()

app = FastAPI(title="PDF Splitter API")

# Thêm CORS middleware để cho phép yêu cầu từ domain của bạn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cho phép tất cả các domain, bạn có thể giới hạn nó nếu cần
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temporary directory to store processed files
TEMP_DIR = os.path.join(tempfile.gettempdir(), "pdf_splitter")
os.makedirs(TEMP_DIR, exist_ok=True)

# Auto-cleanup old files (files older than 1 hour)
MAX_FILE_AGE = int(os.environ.get("MAX_FILE_AGE", 3600))  # 1 hour in seconds

# Lấy domain từ biến môi trường hoặc sử dụng mặc định
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")
BASE_PORT = os.environ.get("PORT", "8000")
BASE_PROTOCOL = os.environ.get("BASE_PROTOCOL", "http")
if BASE_DOMAIN == "localhost":
    BASE_URL = f"{BASE_PROTOCOL}://{BASE_DOMAIN}:{BASE_PORT}"
else:
    BASE_URL = f"{BASE_PROTOCOL}://{BASE_DOMAIN}"

def cleanup_old_files():
    """Remove temporary files older than MAX_FILE_AGE"""
    current_time = time.time()
    for filename in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, filename)
        # Check if file is older than MAX_FILE_AGE
        if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path)) > MAX_FILE_AGE:
            os.remove(file_path)

def is_valid_pdf(file_data):
    """Check if the data is a valid PDF file."""
    try:
        # Try to create a PdfReader object
        if isinstance(file_data, io.BytesIO):
            file_data.seek(0)
        pdf_reader = PyPDF2.PdfReader(file_data)
        # If we can get the number of pages, it's likely a valid PDF
        num_pages = len(pdf_reader.pages)
        if isinstance(file_data, io.BytesIO):
            file_data.seek(0)
        return True
    except Exception as e:
        return False

def download_file_from_url(url):
    """Download file from a given URL."""
    # Check if it's a Google Drive link
    if "drive.google.com" in url:
        return download_from_gdrive(url)
    
    # Regular HTTP URL
    try:
        # Add user agent to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
        }
        
        response = requests.get(url, headers=headers, stream=True, allow_redirects=True)
        response.raise_for_status()
        
        # Get the file content
        file_data = io.BytesIO(response.content)
        
        # Validate that it's actually a PDF
        if not is_valid_pdf(file_data):
            return None, "The downloaded file is not a valid PDF."
            
        return file_data, None
        
    except Exception as e:
        return None, f"Error downloading file: {str(e)}"

def download_from_gdrive(url):
    """Download a file from Google Drive."""
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_path = temp_file.name
        
        # Use gdown to download the file
        output = gdown.download(url=url, output=temp_path, quiet=True, fuzzy=True)
        
        if output is None:
            return None, "Failed to download file from Google Drive."
            
        # Read the file into BytesIO
        with open(temp_path, 'rb') as f:
            file_data = io.BytesIO(f.read())
        
        # Clean up the temporary file
        os.unlink(temp_path)
        
        # Validate PDF
        if not is_valid_pdf(file_data):
            return None, "The downloaded file from Google Drive is not a valid PDF."
            
        return file_data, None
    except Exception as e:
        return None, f"Error downloading from Google Drive: {str(e)}"

def parse_range_input(range_input, max_pages):
    """Parse the range input string and convert to list of tuples."""
    ranges = []
    
    # Handle empty input
    if not range_input or not range_input.strip():
        return ranges
    
    # Split by comma
    parts = range_input.strip().split(',')
    
    for part in parts:
        # Split by hyphen
        try:
            if '-' in part:
                start, end = map(int, part.split('-'))
                if start > 0 and start <= end and start <= max_pages:
                    # Adjust end page to max if it exceeds
                    end = min(end, max_pages)
                    ranges.append((start, end))
            else:
                # Single page
                page = int(part)
                if page > 0 and page <= max_pages:
                    ranges.append((page, page))
        except ValueError:
            # Skip invalid ranges
            continue
    
    return ranges

def split_pdf(input_pdf, ranges):
    """Split a PDF file based on the provided page ranges."""
    if isinstance(input_pdf, str):
        pdf_reader = PyPDF2.PdfReader(input_pdf)
    else:
        pdf_reader = PyPDF2.PdfReader(input_pdf)
    
    total_pages = len(pdf_reader.pages)
    
    # Create a list to store all the split PDFs
    output_pdfs = []
    
    for page_range in ranges:
        start_page, end_page = page_range
        
        # Adjust for zero-based indexing and ensure within bounds
        start_idx = max(0, start_page - 1)
        end_idx = min(end_page, total_pages)
        
        if start_idx < total_pages and start_idx <= end_idx:
            # Create a PDF writer for this range
            pdf_writer = PyPDF2.PdfWriter()
            
            # Add the specified pages
            for page_num in range(start_idx, end_idx):
                pdf_writer.add_page(pdf_reader.pages[page_num])
            
            # Add to our list of output PDFs
            output_pdfs.append(pdf_writer)
    
    return output_pdfs

def save_pdf_to_temp(pdf_writer, range_str):
    """Save PDF writer object to temporary file and return path."""
    # Create a unique filename
    filename = f"split_{range_str}_{uuid.uuid4().hex}.pdf"
    output_path = os.path.join(TEMP_DIR, filename)
    
    # Save the PDF
    with open(output_path, "wb") as output_file:
        pdf_writer.write(output_file)
    
    return output_path

@app.on_event("startup")
async def startup_event():
    # Create temp directory if it doesn't exist
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    # Clean up any old files
    cleanup_old_files()

@app.get("/")
async def root():
    return {"message": "PDF Splitter API is running. Use /docs for API documentation."}

@app.post("/split-pdf-url/")
async def split_pdf_url(
    url: str = Form(...),
    ranges: str = Form(...),
    background_tasks: BackgroundTasks = None
):
    """Split a PDF from a URL by page ranges."""
    # Clean up old files
    cleanup_old_files()
    
    # Download the PDF from URL
    pdf_data, error = download_file_from_url(url)
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    if not pdf_data:
        raise HTTPException(status_code=400, detail="Failed to download valid PDF from URL.")
    
    # Get total pages
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_data)
        total_pages = len(pdf_reader.pages)
        # Reset seek pointer
        pdf_data.seek(0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading PDF: {str(e)}")
    
    # Parse ranges
    range_tuples = parse_range_input(ranges, total_pages)
    if not range_tuples:
        raise HTTPException(status_code=400, detail="No valid page ranges specified.")
    
    # Split the PDF
    try:
        output_pdfs = split_pdf(pdf_data, range_tuples)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error splitting PDF: {str(e)}")
    
    # Save each split PDF and collect download URLs
    result_files = []
    
    for i, pdf_writer in enumerate(output_pdfs):
        range_str = f"{range_tuples[i][0]}-{range_tuples[i][1]}"
        output_path = save_pdf_to_temp(pdf_writer, range_str)
        filename = os.path.basename(output_path)
        
        # Add file to result
        result_files.append({
            "range": range_str,
            "download_url": f"{BASE_URL}/download/{filename}",
            "filename": f"split_{range_str}.pdf"
        })
    
    # Schedule cleanup of temporary files
    if background_tasks:
        background_tasks.add_task(cleanup_old_files)
    
    return JSONResponse(content={
        "message": f"Successfully split PDF into {len(output_pdfs)} files.",
        "total_pages": total_pages,
        "files": result_files
    })

@app.post("/split-pdf-upload/")
async def split_pdf_upload(
    file: UploadFile = File(...),
    ranges: str = Form(...),
    background_tasks: BackgroundTasks = None
):
    """Split an uploaded PDF by page ranges."""
    # Clean up old files
    cleanup_old_files()
    
    # Verify the file is a PDF
    if not file.content_type or "application/pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail="Uploaded file is not a PDF.")
    
    # Save uploaded file to temp location
    temp_file_path = os.path.join(TEMP_DIR, f"upload_{uuid.uuid4().hex}.pdf")
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Get total pages
    try:
        pdf_reader = PyPDF2.PdfReader(temp_file_path)
        total_pages = len(pdf_reader.pages)
    except Exception as e:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise HTTPException(status_code=400, detail=f"Error reading PDF: {str(e)}")
    
    # Parse ranges
    range_tuples = parse_range_input(ranges, total_pages)
    if not range_tuples:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise HTTPException(status_code=400, detail="No valid page ranges specified.")
    
    # Split the PDF
    try:
        output_pdfs = split_pdf(temp_file_path, range_tuples)
    except Exception as e:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Error splitting PDF: {str(e)}")
    
    # Clean up the temporary uploaded file
    if os.path.exists(temp_file_path):
        os.unlink(temp_file_path)
    
    # Save each split PDF and collect download URLs
    result_files = []
    
    for i, pdf_writer in enumerate(output_pdfs):
        range_str = f"{range_tuples[i][0]}-{range_tuples[i][1]}"
        output_path = save_pdf_to_temp(pdf_writer, range_str)
        filename = os.path.basename(output_path)
        
        # Add file to result
        result_files.append({
            "range": range_str,
            "download_url": f"{BASE_URL}/download/{filename}",
            "filename": f"split_{range_str}.pdf"
        })
    
    # Schedule cleanup of temporary files
    if background_tasks:
        background_tasks.add_task(cleanup_old_files)
    
    return JSONResponse(content={
        "message": f"Successfully split PDF into {len(output_pdfs)} files.",
        "total_pages": total_pages,
        "files": result_files
    })

@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download a previously split PDF file."""
    file_path = os.path.join(TEMP_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or expired.")
    
    # Get the original range from the filename to use as the download name
    try:
        range_part = filename.split('_')[1]  # Extract the range part (e.g., "1-5")
        download_name = f"split_{range_part}.pdf"
    except:
        download_name = f"split_pdf.pdf"
    
    return FileResponse(
        path=file_path, 
        filename=download_name,
        media_type="application/pdf"
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)