import streamlit as st
import PyPDF2
import io
import base64
import requests
import tempfile
import os
import re
import gdown
import uuid
import time

# Tạo thư mục tạm thời để lưu trữ các file đã chia
TEMP_DIR = os.path.join(tempfile.gettempdir(), "pdf_splitter")
os.makedirs(TEMP_DIR, exist_ok=True)

# Thời gian hết hạn cho các file tạm (1 giờ)
MAX_FILE_AGE = 3600

def cleanup_old_files():
    """Xóa các file tạm thời cũ hơn MAX_FILE_AGE"""
    current_time = time.time()
    for filename in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, filename)
        if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path)) > MAX_FILE_AGE:
            os.remove(file_path)

def download_file_from_url(url):
    """Download file from a given URL.
    
    Args:
        url: URL to download from
        
    Returns:
        BytesIO object containing the file data
    """
    # Check if it's a Google Drive link
    if "drive.google.com" in url:
        return download_from_gdrive(url)
    
    # Regular HTTP URL
    try:
        # Thêm User-Agent để giả lập trình duyệt
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
        }
        
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '')
        if 'application/pdf' not in content_type.lower():
            st.warning(f"Cảnh báo: URL có thể không phải là file PDF (Content-Type: {content_type})")
        
        return io.BytesIO(response.content)
    except Exception as e:
        st.error(f"Lỗi khi tải file: {str(e)}")
        return None

def download_from_gdrive(url):
    """Download a file from Google Drive.
    
    Args:
        url: Google Drive URL
        
    Returns:
        BytesIO object containing the file data
    """
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_path = temp_file.name
        
        # Use gdown to download the file
        gdown.download(url=url, output=temp_path, quiet=True, fuzzy=True)
        
        # Read the file into BytesIO
        with open(temp_path, 'rb') as f:
            file_data = io.BytesIO(f.read())
        
        # Clean up the temporary file
        os.unlink(temp_path)
        
        return file_data
    except Exception as e:
        st.error(f"Lỗi khi tải từ Google Drive: {str(e)}")
        return None

def split_pdf(input_pdf, ranges):
    """Split a PDF file based on the provided page ranges.
    
    Args:
        input_pdf: The input PDF file (binary)
        ranges: A list of tuples containing (start_page, end_page)
        
    Returns:
        A list of PDF writer objects
    """
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

def parse_range_input(range_input, max_pages):
    """Parse the range input string and convert to list of tuples.
    
    Args:
        range_input: A string like "1-5,8-10,15-20"
        max_pages: Maximum number of pages in the PDF
        
    Returns:
        A list of tuples like [(1, 5), (8, 10), (15, 20)]
    """
    ranges = []
    
    # Handle empty input
    if not range_input.strip():
        return ranges
    
    # Split by comma
    parts = range_input.strip().split(',')
    
    for part in parts:
        # Split by hyphen
        try:
            if '-' in part:
                start, end = map(int, part.split('-'))
                if start > 0 and start <= end:
                    ranges.append((start, end))
            else:
                # Single page
                page = int(part)
                if page > 0:
                    ranges.append((page, page))
        except ValueError:
            # Skip invalid ranges
            continue
    
    return ranges

def get_download_link(pdf_writer, filename):
    """Generate a download link for a PDF."""
    output = io.BytesIO()
    pdf_writer.write(output)
    pdf_bytes = output.getvalue()
    b64 = base64.b64encode(pdf_bytes).decode()
    return f'<a href="data:application/pdf;base64,{b64}" download="{filename}">Download {filename}</a>'

def save_pdf_to_temp(pdf_writer, range_str):
    """Lưu PDF writer object vào file tạm thời và trả về đường dẫn."""
    # Tạo tên file độc nhất
    filename = f"split_{range_str}_{uuid.uuid4().hex}.pdf"
    output_path = os.path.join(TEMP_DIR, filename)
    
    # Lưu PDF
    with open(output_path, "wb") as output_file:
        pdf_writer.write(output_file)
    
    return output_path, filename

def api_split_url(url, ranges_str):
    """Hàm xử lý tách PDF từ URL như một API endpoint.
    
    Args:
        url: URL của file PDF
        ranges_str: Chuỗi các khoảng trang (e.g., "1-5,8-10")
        
    Returns:
        Dict chứa thông tin về các file đã tách
    """
    # Tải file từ URL
    with st.spinner("Đang tải file..."):
        pdf_data = download_file_from_url(url)
        if pdf_data is None:
            return {"error": "Không thể tải PDF từ URL đã cung cấp"}
    
    # Đọc PDF để lấy tổng số trang
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_data)
        total_pages = len(pdf_reader.pages)
        
        # Reset con trỏ file
        pdf_data.seek(0)
    except Exception as e:
        return {"error": f"Lỗi khi đọc PDF: {str(e)}"}
    
    # Phân tích chuỗi khoảng trang
    ranges = parse_range_input(ranges_str, total_pages)
    if not ranges:
        return {"error": "Không có khoảng trang hợp lệ"}
    
    # Tách PDF
    try:
        output_pdfs = split_pdf(pdf_data, ranges)
    except Exception as e:
        return {"error": f"Lỗi khi tách PDF: {str(e)}"}
    
    # Lưu từng file PDF đã tách và thu thập URL tải xuống
    result_files = []
    
    for i, pdf_writer in enumerate(output_pdfs):
        range_str = f"{ranges[i][0]}-{ranges[i][1]}"
        output_path, filename = save_pdf_to_temp(pdf_writer, range_str)
        
        # Tạo link tải xuống
        download_link = get_download_link(pdf_writer, f"split_{range_str}.pdf")
        
        # Thêm file vào kết quả
        result_files.append({
            "range": range_str,
            "filename": f"split_{range_str}.pdf",
            "download_link": download_link
        })
    
    return {
        "success": True,
        "message": f"Đã tách PDF thành {len(output_pdfs)} file.",
        "total_pages": total_pages,
        "files": result_files
    }

def main():
    st.set_page_config(page_title="PDF Splitter", layout="wide")
    
    # Dọn dẹp file cũ
    cleanup_old_files()
    
    st.title("PDF Splitter Tool")
    st.write("Tải lên PDF hoặc cung cấp URL và chỉ định các khoảng trang để tách ra")
    
    # Tạo tabs cho các phương thức nhập khác nhau
    tab1, tab2, tab3 = st.tabs(["Tải lên File", "Từ URL", "URL & Range nhanh"])
    
    # Tab 1: Tải file lên từ máy tính
    with tab1:
        uploaded_file = st.file_uploader("Chọn file PDF", type="pdf")
        if uploaded_file is not None:
            # Đọc PDF để lấy tổng số trang
            try:
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                total_pages = len(pdf_reader.pages)
                st.success(f"Tải lên thành công! PDF có {total_pages} trang.")
                
                # Reset con trỏ file
                uploaded_file.seek(0)
                
                # Nhập khoảng trang
                range_input = st.text_input(
                    "Nhập khoảng trang (ví dụ: 1-5,8-10,15-20):",
                    key="range_upload",
                    help="Định dạng: start-end,start-end,... (ví dụ: 1-5,8-10,15-20)"
                )
                
                if st.button("Tách PDF", key="split_upload"):
                    if range_input:
                        with st.spinner("Đang xử lý..."):
                            ranges = parse_range_input(range_input, total_pages)
                            
                            if ranges:
                                # Tách PDF
                                output_pdfs = split_pdf(uploaded_file, ranges)
                                
                                if output_pdfs:
                                    st.success(f"Đã tách PDF thành {len(output_pdfs)} file!")
                                    
                                    # Cung cấp link tải xuống
                                    download_container = st.container()
                                    with download_container:
                                        st.write("### File tải xuống")
                                        for i, pdf_writer in enumerate(output_pdfs):
                                            range_str = f"{ranges[i][0]}-{ranges[i][1]}"
                                            filename = f"split_{range_str}.pdf"
                                            
                                            download_link = get_download_link(pdf_writer, filename)
                                            st.markdown(download_link, unsafe_allow_html=True)
                                else:
                                    st.error("Không thể tách PDF. Vui lòng kiểm tra khoảng trang.")
                            else:
                                st.error("Vui lòng nhập khoảng trang hợp lệ.")
                    else:
                        st.error("Vui lòng nhập khoảng trang để tách PDF.")
            except Exception as e:
                st.error(f"Lỗi khi xử lý PDF: {str(e)}")
    
    # Tab 2: Từ URL (như phiên bản cũ)
    with tab2:
        url = st.text_input("Nhập URL của PDF (hỗ trợ link trực tiếp và Google Drive):", key="url_tab2")
        url_help = """
        Hỗ trợ:
        - Link HTTP/HTTPS trực tiếp đến file PDF
        - Link Google Drive (chỉ file công khai)
        """
        st.markdown(url_help)
        
        fetch_pdf = st.button("Tải PDF", key="fetch_tab2")
        
        if fetch_pdf and url:
            with st.spinner("Đang tải file..."):
                pdf_data = download_file_from_url(url)
                if pdf_data:
                    # Đọc PDF để lấy tổng số trang
                    try:
                        pdf_reader = PyPDF2.PdfReader(pdf_data)
                        total_pages = len(pdf_reader.pages)
                        st.session_state.pdf_data = pdf_data
                        st.session_state.total_pages = total_pages
                        st.success(f"Tải file thành công! PDF có {total_pages} trang.")
                        
                        # Nhập khoảng trang
                        range_input = st.text_input(
                            "Nhập khoảng trang (ví dụ: 1-5,8-10,15-20):",
                            key="range_tab2",
                            help="Định dạng: start-end,start-end,... (ví dụ: 1-5,8-10,15-20)"
                        )
                        
                        if st.button("Tách PDF", key="split_tab2"):
                            if range_input:
                                with st.spinner("Đang xử lý..."):
                                    ranges = parse_range_input(range_input, total_pages)
                                    
                                    if ranges:
                                        # Tách PDF
                                        output_pdfs = split_pdf(pdf_data, ranges)
                                        
                                        if output_pdfs:
                                            st.success(f"Đã tách PDF thành {len(output_pdfs)} file!")
                                            
                                            # Cung cấp link tải xuống
                                            download_container = st.container()
                                            with download_container:
                                                st.write("### File tải xuống")
                                                for i, pdf_writer in enumerate(output_pdfs):
                                                    range_str = f"{ranges[i][0]}-{ranges[i][1]}"
                                                    filename = f"split_{range_str}.pdf"
                                                    
                                                    download_link = get_download_link(pdf_writer, filename)
                                                    st.markdown(download_link, unsafe_allow_html=True)
                                        else:
                                            st.error("Không thể tách PDF. Vui lòng kiểm tra khoảng trang.")
                                    else:
                                        st.error("Vui lòng nhập khoảng trang hợp lệ.")
                            else:
                                st.error("Vui lòng nhập khoảng trang để tách PDF.")
                    except Exception as e:
                        st.error(f"Lỗi khi xử lý PDF: {str(e)}")
        elif fetch_pdf:
            st.error("Vui lòng nhập URL")
    
    # Tab 3: URL & Range nhanh (phương thức mới)
    with tab3:
        st.write("Nhập URL và khoảng trang để tách PDF ngay lập tức")
        url_quick = st.text_input("URL của file PDF:", key="url_quick")
        range_quick = st.text_input("Khoảng trang (ví dụ: 12-21,21-30):", key="range_quick")
        
        if st.button("Tách PDF ngay", key="split_quick"):
            if url_quick and range_quick:
                with st.spinner("Đang xử lý..."):
                    # Gọi hàm xử lý như API
                    result = api_split_url(url_quick, range_quick)
                    
                    if "error" in result:
                        st.error(result["error"])
                    else:
                        st.success(result["message"])
                        st.write(f"Tổng số trang: {result['total_pages']}")
                        
                        # Hiển thị các file đã tách
                        file_container = st.container()
                        with file_container:
                            st.write("### File đã tách")
                            for file_info in result["files"]:
                                st.write(f"**Trang {file_info['range']}:**")
                                st.markdown(file_info["download_link"], unsafe_allow_html=True)
                                st.write("---")
            else:
                if not url_quick:
                    st.error("Vui lòng nhập URL của file PDF")
                if not range_quick:
                    st.error("Vui lòng nhập khoảng trang cần tách")

if __name__ == "__main__":
    main()