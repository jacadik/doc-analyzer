import os
import re
import json
import logging
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
import docx
import hashlib
from datetime import datetime

# Set up logger
logger = logging.getLogger(__name__)

def allowed_file(filename, allowed_extensions):
    """Check if a file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_uploaded_file(file, upload_folder, allowed_extensions):
    """Save an uploaded file to the configured upload folder"""
    # Handle case where file is a list (multiple file upload)
    if isinstance(file, list):
        if not file:  # Empty list
            return None
        file = file[0]  # Take the first file
    
    if file and hasattr(file, 'filename') and allowed_file(file.filename, allowed_extensions):
        # Secure the filename
        original_filename = file.filename
        # Add timestamp to avoid filename conflicts
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = secure_filename(f"{timestamp}_{original_filename}")
        file_path = os.path.join(upload_folder, filename)
        
        # Save the file
        file.save(file_path)
        
        # Get file size and type
        file_size = os.path.getsize(file_path)
        file_type = original_filename.rsplit('.', 1)[1].lower()
        
        logger.info(f"File saved: {file_path}, Size: {file_size} bytes")
        
        return {
            'filename': filename,
            'original_filename': original_filename,
            'file_path': file_path,
            'file_type': file_type,
            'file_size': file_size
        }
    
    return None

def extract_text_from_pdf(file_path):
    """Extract text and basic layout information from a PDF file"""
    try:
        logger.info(f"Extracting text from PDF: {file_path}")
        doc = fitz.open(file_path)
        
        # Initialize text and layout containers
        full_text = ""
        layout_info = {
            'pages': [],
            'page_count': len(doc)
        }
        
        # Process each page
        for page_num, page in enumerate(doc):
            # Extract text from page
            page_text = page.get_text()
            full_text += page_text + "\n\n"
            
            # Get page dimensions
            page_info = {
                'page_num': page_num + 1,
                'width': page.rect.width,
                'height': page.rect.height,
                'blocks': []
            }
            
            # Extract text blocks with positions
            blocks = page.get_text("blocks")
            for block_num, block in enumerate(blocks):
                # block[0:4] are coordinates (x0, y0, x1, y1)
                # block[4] is the text content
                x0, y0, x1, y1, text = block[0:5]
                
                # Add block info to page
                page_info['blocks'].append({
                    'block_num': block_num + 1,
                    'x0': x0,
                    'y0': y0,
                    'x1': x1,
                    'y1': y1,
                    'text': text
                })
            
            # Add page info to layout
            layout_info['pages'].append(page_info)
        
        # Close the document
        doc.close()
        
        return {
            'full_text': full_text,
            'layout_info': json.dumps(layout_info),
            'page_count': layout_info['page_count']
        }
    
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}", exc_info=True)
        return {
            'full_text': None,
            'layout_info': None,
            'page_count': 0,
            'error': str(e)
        }

def extract_text_from_docx(file_path):
    """Extract text and basic structure information from a Word document"""
    try:
        logger.info(f"Extracting text from DOCX: {file_path}")
        doc = docx.Document(file_path)
        
        # Initialize text and layout containers
        full_text = ""
        layout_info = {
            'pages': [],  # Can't reliably determine pages in DOCX
            'page_count': 0,  # We'll estimate this
            'paragraphs': []
        }
        
        # Process paragraphs
        for para_num, para in enumerate(doc.paragraphs):
            if para.text.strip():  # Skip empty paragraphs
                full_text += para.text + "\n\n"
                
                # Add paragraph info to layout
                layout_info['paragraphs'].append({
                    'para_num': para_num + 1,
                    'text': para.text,
                    'style': para.style.name if para.style else 'Normal'
                })
        
        # Estimate page count (rough estimate based on character count)
        avg_chars_per_page = 2000  # Adjust based on your documents
        layout_info['page_count'] = max(1, len(full_text) // avg_chars_per_page)
        
        return {
            'full_text': full_text,
            'layout_info': json.dumps(layout_info),
            'page_count': layout_info['page_count']
        }
    
    except Exception as e:
        logger.error(f"Error extracting text from DOCX: {e}", exc_info=True)
        return {
            'full_text': None,
            'layout_info': None,
            'page_count': 0,
            'error': str(e)
        }

def segment_paragraphs(text):
    """Split text into paragraphs based on double newlines or other paragraph breaks"""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Split on paragraph boundaries (double newlines, etc.)
    paragraphs = re.split(r'\n\s*\n|\r\n\s*\r\n', text)
    
    # Clean up paragraphs
    cleaned_paragraphs = []
    for para in paragraphs:
        para = para.strip()
        if para:  # Skip empty paragraphs
            cleaned_paragraphs.append(para)
    
    return cleaned_paragraphs

def find_variables(text, patterns):
    """Find variable placeholders in text using regex patterns"""
    variables = []
    
    for pattern in patterns:
        if pattern == r'<<([^>]+)>>':
            pattern_type = '<<>>'
            regex = re.compile(pattern)
        elif pattern == r'\{\{([^}]+)\}\}':
            pattern_type = '{{}}'
            regex = re.compile(pattern)
        elif pattern == r'\$\{([^}]+)\}':
            pattern_type = '${}'
            regex = re.compile(pattern)
        else:
            continue
        
        # Find all matches
        for match in regex.finditer(text):
            variable_name = match.group(1).strip()
            if variable_name:
                variables.append({
                    'name': variable_name,
                    'pattern_type': pattern_type,
                    'full_match': match.group(0)
                })
    
    return variables

def process_document(file_path, file_type, variable_patterns):
    """Process a document to extract text, paragraphs, and variables"""
    try:
        logger.info(f"Processing document: {file_path}, Type: {file_type}")
        
        # Extract text based on file type
        if file_type == 'pdf':
            extraction_result = extract_text_from_pdf(file_path)
        elif file_type == 'docx':
            extraction_result = extract_text_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
        
        if 'error' in extraction_result:
            return {
                'success': False,
                'error': extraction_result['error']
            }
        
        full_text = extraction_result['full_text']
        layout_info = extraction_result['layout_info']
        page_count = extraction_result['page_count']
        
        # Segment text into paragraphs
        paragraphs = segment_paragraphs(full_text)
        
        # Create paragraph objects with hash for comparison
        paragraph_objects = []
        for i, para_text in enumerate(paragraphs):
            # Skip extremely short paragraphs (likely noise)
            if len(para_text) < 5:
                continue
                
            # Generate hash for paragraph
            para_hash = hashlib.sha256(para_text.encode('utf-8')).hexdigest()
            
            paragraph_objects.append({
                'text': para_text,
                'hash': para_hash,
                'position': i
            })
        
        # Find variables
        variables = find_variables(full_text, variable_patterns)
        
        # Return processing results
        return {
            'success': True,
            'full_text': full_text,
            'layout_info': layout_info,
            'page_count': page_count,
            'paragraphs': paragraph_objects,
            'variables': variables
        }
    
    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }
