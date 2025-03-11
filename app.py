import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_bootstrap import Bootstrap5
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import SubmitField, BooleanField, IntegerField, MultipleFileField
from werkzeug.utils import secure_filename
from config import Config
from models import db, Document, Paragraph, Variable
from utils.document import save_uploaded_file, process_document
from utils.analyzer import find_exact_duplicates, find_similar_paragraphs, analyze_variable_usage, get_paragraph_statistics, extract_common_phrases
from utils.export import export_documents_to_excel, export_analysis_to_excel, export_templates_to_excel, export_variables_to_excel
import json
from datetime import datetime
import time
import threading

# File upload form
class UploadForm(FlaskForm):
    file = FileField('Document File', validators=[
        FileRequired(),
        FileAllowed(['pdf', 'docx'], 'Only PDF and DOCX files are allowed!')
    ])
    submit = SubmitField('Upload')

# Bulk Upload Form
class BulkUploadForm(FlaskForm):
    files = MultipleFileField('Select Files', validators=[
        FileAllowed(['pdf', 'docx'], 'Only PDF and DOCX files are allowed!')
    ])
    folder = MultipleFileField('Select Folder') # Changed to MultipleFileField to support folder uploads
    process_immediately = BooleanField('Process Immediately After Upload', default=True)
    enable_batch_size = BooleanField('Enable Batch Processing')
    batch_size = IntegerField('Batch Size (5-100)', default=20)
    submit = SubmitField('Upload')

# Create and configure Flask app
app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

# Initialize extensions
bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)
db.init_app(app)

# Document Processing Queue Class
class DocumentProcessingQueue:
    def __init__(self, max_workers=4):
        self.queue = []
        self.is_processing = False
        self.is_paused = False
        self.max_workers = max_workers
        self.batch_size = 20
        self.processed_count = 0
        self.error_count = 0
        self.threads = []
        self.lock = threading.Lock()
    
    def add_documents(self, doc_ids):
        """Add document IDs to the processing queue"""
        with self.lock:
            # Filter out duplicates
            new_ids = [doc_id for doc_id in doc_ids if doc_id not in self.queue]
            self.queue.extend(new_ids)
            return len(new_ids)
    
    def start(self, batch_size=None):
        """Start processing documents in the queue"""
        if batch_size is not None:
            self.batch_size = max(5, min(100, batch_size))
        
        if not self.is_processing and not self.is_paused:
            self.is_processing = True
            for _ in range(self.max_workers):
                thread = threading.Thread(target=self._process_documents)
                thread.daemon = True
                thread.start()
                self.threads.append(thread)
            return True
        return False
    
    def pause(self):
        """Pause queue processing"""
        if self.is_processing and not self.is_paused:
            self.is_paused = True
            return True
        return False
    
    def resume(self):
        """Resume queue processing after pausing"""
        if self.is_paused:
            self.is_paused = False
            return True
        return False
    
    def clear_queue(self):
        """Clear the processing queue"""
        with self.lock:
            self.queue = []
            return True
    
    def get_status(self):
        """Get current status of the processing queue"""
        with self.lock:
            return {
                'queue_length': len(self.queue),
                'is_processing': self.is_processing,
                'is_paused': self.is_paused,
                'workers': self.max_workers,
                'batch_size': self.batch_size,
                'processed_count': self.processed_count,
                'error_count': self.error_count
            }
    
    def _process_documents(self):
        """Worker thread function to process documents"""
        while self.is_processing:
            if self.is_paused:
                time.sleep(1)
                continue
            
            doc_id = None
            with self.lock:
                if self.queue:
                    doc_id = self.queue.pop(0)
            
            if doc_id is not None:
                try:
                    with app.app_context():
                        document = Document.query.get(doc_id)
                        if not document:
                            continue
                        
                        # Get file path
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], document.filename)
                        if not os.path.exists(file_path):
                            error_msg = f"File {file_path} does not exist"
                            document.processing_error = error_msg
                            db.session.commit()
                            with self.lock:
                                self.error_count += 1
                            continue
                        
                        # Process document
                        result = process_document(
                            file_path, 
                            document.file_type,
                            app.config['VARIABLE_PATTERNS']
                        )
                        
                        if not result['success']:
                            document.processing_error = result['error']
                            db.session.commit()
                            with self.lock:
                                self.error_count += 1
                            continue
                        
                        # Update document with extracted info
                        document.full_text = result['full_text']
                        document.layout_info = result['layout_info']
                        document.page_count = result['page_count']
                        
                        # Process paragraphs
                        for para_data in result['paragraphs']:
                            # Check if paragraph already exists
                            existing_para = Paragraph.query.filter_by(hash=para_data['hash']).first()
                            
                            if existing_para:
                                # Use existing paragraph
                                para = existing_para
                            else:
                                # Create new paragraph
                                para = Paragraph(
                                    text=para_data['text'],
                                    hash=para_data['hash'],
                                    position=para_data['position']
                                )
                                db.session.add(para)
                            
                            # Add paragraph to document if not already there
                            if para not in document.paragraphs:
                                document.paragraphs.append(para)
                        
                        # Process variables
                        for var_data in result['variables']:
                            # Check if variable already exists
                            existing_var = Variable.query.filter_by(
                                name=var_data['name'], 
                                pattern_type=var_data['pattern_type']
                            ).first()
                            
                            if existing_var:
                                # Use existing variable
                                var = existing_var
                            else:
                                # Create new variable
                                var = Variable(
                                    name=var_data['name'],
                                    pattern_type=var_data['pattern_type']
                                )
                                db.session.add(var)
                            
                            # Add variable to document if not already there
                            if var not in document.variables:
                                document.variables.append(var)
                        
                        # Mark as processed
                        document.processed = True
                        db.session.commit()
                        
                        with self.lock:
                            self.processed_count += 1
                except Exception as e:
                    app.logger.error(f"Error processing document {doc_id}: {e}", exc_info=True)
                    # Update document status
                    with app.app_context():
                        document = Document.query.get(doc_id)
                        if document:
                            document.processing_error = str(e)
                            db.session.commit()
                    with self.lock:
                        self.error_count += 1
            else:
                time.sleep(1)  # Sleep when queue is empty

# Create document processing queue with 4 worker threads
doc_queue = DocumentProcessingQueue(max_workers=4)

# Create tables and initialize app (Flask 2.x compatible)
def create_tables():
    with app.app_context():
        db.create_all()
        # Ensure export directory exists
        os.makedirs('exports', exist_ok=True)
        # Start background processing thread
        doc_queue.start()

# Call the initialization function immediately
create_tables()

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error=e, title='Page Not Found'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error=e, title='Server Error'), 500

# Routes
@app.route('/')
def index():
    """Home page"""
    # Count documents, paragraphs, and variables
    doc_count = Document.query.count()
    para_count = Paragraph.query.count()
    var_count = Variable.query.count()
    
    # Get processing status
    processing_count = Document.query.filter_by(processed=False).filter(Document.processing_error.is_(None)).count()
    error_count = Document.query.filter(Document.processing_error.isnot(None)).count()
    
    # Recent documents
    recent_docs = Document.query.order_by(Document.upload_date.desc()).limit(5).all()
    
    return render_template('index.html',
                          doc_count=doc_count,
                          para_count=para_count,
                          var_count=var_count,
                          processing_count=processing_count,
                          error_count=error_count,
                          recent_docs=recent_docs)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Enhanced upload document page with bulk support"""
    form = BulkUploadForm()
    
    if request.method == 'POST':
        # Process immediately flag
        process_immediately = 'process_immediately' in request.form
        
        # Batch size processing
        enable_batch_size = 'enable_batch_size' in request.form
        batch_size = 20  # Default batch size
        
        if enable_batch_size:
            try:
                batch_size = int(request.form.get('batch_size', 20))
                batch_size = max(5, min(100, batch_size))  # Limit between 5-100
            except ValueError:
                pass
        
        # Check which form is being submitted
        uploaded_docs = []
        failed_files = []
        
        if 'files' in request.files:  # Regular file upload
            files = request.files.getlist('files')
            
            if not files or files[0].filename == '':
                flash('No files selected.', 'danger')
                return render_template('upload.html', form=form)
            
            # Process all valid files
            for file in files:
                if file and file.filename and allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']):
                    try:
                        result = save_uploaded_file(file, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS'])
                        
                        if result:
                            # Create document record
                            document = Document(
                                filename=result['filename'],
                                original_filename=result['original_filename'],
                                file_type=result['file_type'],
                                file_size=result['file_size']
                            )
                            
                            # Save to database
                            db.session.add(document)
                            db.session.commit()
                            
                            # Add to processed list
                            uploaded_docs.append(document)
                        else:
                            failed_files.append(file.filename)
                    except Exception as e:
                        app.logger.error(f"Error uploading file {file.filename}: {e}", exc_info=True)
                        failed_files.append(file.filename)
                else:
                    if file and file.filename:
                        failed_files.append(file.filename)
            
        elif 'folder' in request.files:  # Folder upload
            files = request.files.getlist('folder')
            
            if not files or files[0].filename == '':
                flash('No folder selected or folder is empty.', 'danger')
                return render_template('upload.html', form=form)
            
            # Filter for valid files (PDF and DOCX)
            valid_files = []
            for file in files:
                if file and file.filename:
                    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                    if file_ext in app.config['ALLOWED_EXTENSIONS']:
                        valid_files.append(file)
            
            if not valid_files:
                flash('No valid PDF or DOCX files found in the folder.', 'warning')
                return render_template('upload.html', form=form)
            
            # Process all valid files
            for file in valid_files:
                try:
                    result = save_uploaded_file(file, app.config['UPLOAD_FOLDER'], app.config['ALLOWED_EXTENSIONS'])
                    
                    if result:
                        # Create document record
                        document = Document(
                            filename=result['filename'],
                            original_filename=result['original_filename'],
                            file_type=result['file_type'],
                            file_size=result['file_size']
                        )
                        
                        # Save to database
                        db.session.add(document)
                        db.session.commit()
                        
                        # Add to processed list
                        uploaded_docs.append(document)
                    else:
                        failed_files.append(file.filename)
                except Exception as e:
                    app.logger.error(f"Error uploading file {file.filename}: {e}", exc_info=True)
                    failed_files.append(file.filename)
        
        # Add to processing queue if needed
        if process_immediately and uploaded_docs:
            doc_ids = [doc.id for doc in uploaded_docs]
            doc_queue.add_documents(doc_ids)
            
            if enable_batch_size:
                doc_queue.batch_size = batch_size
            
            # Start queue if not already running
            if not doc_queue.is_processing or doc_queue.is_paused:
                doc_queue.resume() if doc_queue.is_paused else doc_queue.start()
        
        # Flash message
        if uploaded_docs:
            flash(f'Successfully uploaded {len(uploaded_docs)} documents.', 'success')
            if failed_files:
                flash(f'Failed to upload {len(failed_files)} files.', 'warning')
        else:
            flash('Failed to upload any documents.', 'danger')
        
        return redirect(url_for('documents'))
    
    # GET request - render the upload form
    return render_template('upload.html', form=form)

@app.route('/documents')
def documents():
    """Document list page"""
    # Get query parameters
    sort_by = request.args.get('sort', 'upload_date')
    order = request.args.get('order', 'desc')
    filter_type = request.args.get('type', 'all')
    filter_status = request.args.get('status', 'all')
    
    # Base query
    query = Document.query
    
    # Apply filters
    if filter_type != 'all':
        query = query.filter_by(file_type=filter_type)
    
    if filter_status == 'processed':
        query = query.filter_by(processed=True).filter(Document.processing_error.is_(None))
    elif filter_status == 'processing':
        query = query.filter_by(processed=False).filter(Document.processing_error.is_(None))
    elif filter_status == 'error':
        query = query.filter(Document.processing_error.isnot(None))
    
    # Apply sorting
    if sort_by == 'upload_date':
        query = query.order_by(Document.upload_date.desc() if order == 'desc' else Document.upload_date.asc())
    elif sort_by == 'filename':
        query = query.order_by(Document.original_filename.desc() if order == 'desc' else Document.original_filename.asc())
    elif sort_by == 'file_size':
        query = query.order_by(Document.file_size.desc() if order == 'desc' else Document.file_size.asc())
    elif sort_by == 'page_count':
        query = query.order_by(Document.page_count.desc() if order == 'desc' else Document.page_count.asc())
    
    # Get documents
    documents = query.all()
    
    return render_template('documents.html', 
                          documents=documents,
                          sort_by=sort_by,
                          order=order,
                          filter_type=filter_type,
                          filter_status=filter_status)

@app.route('/document/<int:doc_id>')
def document_view(doc_id):
    """Document view page"""
    document = Document.query.get_or_404(doc_id)
    
    # Load layout info if available
    layout = None
    if document.layout_info:
        try:
            layout = json.loads(document.layout_info)
        except:
            app.logger.error(f"Error parsing layout info for document {doc_id}")
    
    return render_template('document_view.html', document=document, layout=layout)

@app.route('/document/<int:doc_id>/text')
def document_text(doc_id):
    """View document text"""
    document = Document.query.get_or_404(doc_id)
    return render_template('document_text.html', document=document)

@app.route('/document/<int:doc_id>/paragraphs')
def document_paragraphs(doc_id):
    """View document paragraphs"""
    document = Document.query.get_or_404(doc_id)
    
    # Get paragraphs
    paragraphs = document.paragraphs
    
    # Get paragraph statistics
    stats = get_paragraph_statistics([{'text': p.text} for p in paragraphs])
    
    return render_template('document_paragraphs.html', 
                          document=document, 
                          paragraphs=paragraphs,
                          stats=stats)

@app.route('/document/<int:doc_id>/variables')
def document_variables(doc_id):
    """View document variables"""
    document = Document.query.get_or_404(doc_id)
    
    # Get variables
    variables = document.variables
    
    return render_template('document_variables.html', document=document, variables=variables)

@app.route('/document/<int:doc_id>/analyze')
def document_analyze(doc_id):
    """Analyze document for similarities"""
    document = Document.query.get_or_404(doc_id)
    
    # Get paragraphs
    paragraphs = document.paragraphs
    
    # Find similar paragraphs
    threshold = float(request.args.get('threshold', app.config['SIMILARITY_THRESHOLD']))
    
    # Convert paragraphs to the format expected by the analyzer
    para_data = [{'text': p.text, 'hash': p.hash, 'id': p.id} for p in paragraphs]
    
    # Find exact duplicates within this document
    duplicate_groups = find_exact_duplicates(para_data)
    
    # Find similar (but not exact) paragraphs
    similar_pairs = find_similar_paragraphs(para_data, threshold)
    
    # Extract common phrases
    common_phrases = extract_common_phrases(para_data)
    
    return render_template('document_analyze.html',
                          document=document,
                          duplicate_groups=duplicate_groups,
                          similar_pairs=similar_pairs,
                          common_phrases=common_phrases,
                          threshold=threshold)

@app.route('/paragraphs')
def paragraphs():
    """View all paragraphs"""
    # Get query parameters
    sort_by = request.args.get('sort', 'document_count')
    order = request.args.get('order', 'desc')
    min_docs = int(request.args.get('min_docs', 1))
    
    # Base query
    query = Paragraph.query
    
    # Filter by document count
    if min_docs > 1:
        query = query.join(Paragraph.documents).group_by(Paragraph.id).having(db.func.count(Document.id) >= min_docs)
    
    # Apply sorting
    if sort_by == 'document_count':
        # This requires a subquery for proper sorting
        subquery = db.session.query(
            document_paragraph.c.paragraph_id,
            db.func.count(document_paragraph.c.document_id).label('doc_count')
        ).group_by(document_paragraph.c.paragraph_id).subquery()
        
        query = query.outerjoin(
            subquery, 
            Paragraph.id == subquery.c.paragraph_id
        )
        
        if order == 'desc':
            query = query.order_by(db.desc(subquery.c.doc_count))
        else:
            query = query.order_by(subquery.c.doc_count)
    elif sort_by == 'length':
        query = query.order_by(db.func.length(Paragraph.text).desc() if order == 'desc' else db.func.length(Paragraph.text))
    
    # Get paragraphs (limit to reasonable number)
    paragraphs = query.limit(100).all()
    
    return render_template('paragraphs.html',
                          paragraphs=paragraphs,
                          sort_by=sort_by,
                          order=order,
                          min_docs=min_docs)

@app.route('/variables')
def variables():
    """View all variables"""
    # Get query parameters
    sort_by = request.args.get('sort', 'document_count')
    order = request.args.get('order', 'desc')
    
    # Base query
    query = Variable.query
    
    # Apply sorting
    if sort_by == 'document_count':
        # This requires a subquery for proper sorting
        subquery = db.session.query(
            document_variable.c.variable_id,
            db.func.count(document_variable.c.document_id).label('doc_count')
        ).group_by(document_variable.c.variable_id).subquery()
        
        query = query.outerjoin(
            subquery, 
            Variable.id == subquery.c.variable_id
        )
        
        if order == 'desc':
            query = query.order_by(db.desc(subquery.c.doc_count))
        else:
            query = query.order_by(subquery.c.doc_count)
    elif sort_by == 'name':
        query = query.order_by(Variable.name.desc() if order == 'desc' else Variable.name)
    
    # Get variables
    variables = query.all()
    
    return render_template('variables.html',
                          variables=variables,
                          sort_by=sort_by,
                          order=order)

@app.route('/templates')
def templates():
    """View template analysis"""
    # Get all processed documents
    documents = Document.query.filter_by(processed=True).all()
    
    # Group by page count (simplified template detection)
    template_groups = {}
    for doc in documents:
        key = f"{doc.page_count} pages"
        if key in template_groups:
            template_groups[key].append(doc)
        else:
            template_groups[key] = [doc]
    
    return render_template('templates.html', template_groups=template_groups)

@app.route('/export/documents')
def export_documents():
    """Export documents to Excel"""
    documents = Document.query.all()
    filepath = export_documents_to_excel(documents)
    
    if filepath:
        return send_file(filepath, as_attachment=True)
    
    flash('Failed to export documents.', 'danger')
    return redirect(url_for('documents'))

@app.route('/export/document/<int:doc_id>')
def export_document(doc_id):
    """Export document analysis to Excel"""
    document = Document.query.get_or_404(doc_id)
    
    # Get paragraphs and variables
    paragraphs = document.paragraphs
    variables = document.variables
    
    # Get similar paragraphs
    para_data = [{'text': p.text, 'hash': p.hash, 'id': p.id} for p in paragraphs]
    similar_pairs = find_similar_paragraphs(para_data)
    
    # Convert to format expected by export function
    similar_paragraphs = []
    for pair in similar_pairs:
        para1_id = pair['para1']['id']
        para2_id = pair['para2']['id']
        para1 = Paragraph.query.get(para1_id)
        para2 = Paragraph.query.get(para2_id)
        similar_paragraphs.append((para1, para2, pair['similarity']))
    
    filepath = export_analysis_to_excel(document, paragraphs, variables, similar_paragraphs)
    
    if filepath:
        return send_file(filepath, as_attachment=True)
    
    flash('Failed to export document analysis.', 'danger')
    return redirect(url_for('document_view', doc_id=doc_id))

@app.route('/export/templates')
def export_template_analysis():
    """Export template analysis to Excel"""
    documents = Document.query.filter_by(processed=True).all()
    filepath = export_templates_to_excel(documents)
    
    if filepath:
        return send_file(filepath, as_attachment=True)
    
    flash('Failed to export template analysis.', 'danger')
    return redirect(url_for('templates'))

@app.route('/export/variables')
def export_variable_analysis():
    """Export variables to Excel"""
    variables = Variable.query.all()
    filepath = export_variables_to_excel(variables)
    
    if filepath:
        return send_file(filepath, as_attachment=True)
    
    flash('Failed to export variables.', 'danger')
    return redirect(url_for('variables'))

@app.route('/delete/document/<int:doc_id>', methods=['POST'])
def delete_document(doc_id):
    """Delete document"""
    document = Document.query.get_or_404(doc_id)
    
    try:
        # Delete file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], document.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete from database
        db.session.delete(document)
        db.session.commit()
        
        flash(f'Document {document.original_filename} deleted.', 'success')
    except Exception as e:
        app.logger.error(f"Error deleting document {doc_id}: {e}", exc_info=True)
        flash(f'Error deleting document: {e}', 'danger')
    
    return redirect(url_for('documents'))

@app.route('/api/status')
def api_status():
    """API endpoint for checking processing status"""
    # Count documents by status
    total = Document.query.count()
    processed = Document.query.filter_by(processed=True).count()
    processing = Document.query.filter_by(processed=False).filter(Document.processing_error.is_(None)).count()
    error = Document.query.filter(Document.processing_error.isnot(None)).count()
    
    # Get queue status
    queue_status = doc_queue.get_status()
    
    return jsonify({
        'total': total,
        'processed': processed,
        'processing': processing,
        'error': error,
        'queue_length': queue_status['queue_length'],
        'is_processing': queue_status['is_processing']
    })

# New API routes for queue management
@app.route('/api/queue/status', methods=['GET'])
def api_queue_status():
    """API endpoint for checking queue status"""
    return jsonify(doc_queue.get_status())

@app.route('/api/queue/start', methods=['POST'])
def api_queue_start():
    """API endpoint for starting queue processing"""
    batch_size = request.json.get('batch_size') if request.is_json else None
    success = doc_queue.start(batch_size)
    return jsonify({
        'success': success,
        'status': doc_queue.get_status()
    })

@app.route('/api/queue/pause', methods=['POST'])
def api_queue_pause():
    """API endpoint for pausing queue processing"""
    success = doc_queue.pause()
    return jsonify({
        'success': success,
        'status': doc_queue.get_status()
    })

@app.route('/api/queue/resume', methods=['POST'])
def api_queue_resume():
    """API endpoint for resuming queue processing"""
    success = doc_queue.resume()
    return jsonify({
        'success': success,
        'status': doc_queue.get_status()
    })

@app.route('/api/queue/clear', methods=['POST'])
def api_queue_clear():
    """API endpoint for clearing the queue"""
    success = doc_queue.clear_queue()
    return jsonify({
        'success': success,
        'status': doc_queue.get_status()
    })

@app.route('/api/system/stats', methods=['GET'])
def api_system_stats():
    """API endpoint for system statistics"""
    try:
        import psutil
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used = memory.used / (1024 * 1024 * 1024)  # Convert to GB
        memory_total = memory.total / (1024 * 1024 * 1024)  # Convert to GB
        
        # Get disk usage for the uploads folder
        disk = psutil.disk_usage(app.config['UPLOAD_FOLDER'])
        disk_percent = disk.percent
        disk_used = disk.used / (1024 * 1024 * 1024)  # Convert to GB
        disk_total = disk.total / (1024 * 1024 * 1024)  # Convert to GB
        
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # Get uptime
        uptime = time.time() - psutil.boot_time()
        uptime_hours = uptime / 3600
        
        return jsonify({
            'memory': {
                'percent': memory_percent,
                'used': memory_used,
                'total': round(memory_total)
            },
            'disk': {
                'percent': disk_percent,
                'used': disk_used,
                'total': round(disk_total)
            },
            'cpu': {
                'percent': cpu_percent
            },
            'uptime': uptime_hours
        })
    except ImportError:
        # If psutil is not available, return mock data
        return jsonify({
            'memory': {
                'percent': 50,
                'used': 8,
                'total': 16
            },
            'disk': {
                'percent': 45,
                'used': 45,
                'total': 100
            },
            'cpu': {
                'percent': 30
            },
            'uptime': 48
        })
    except Exception as e:
        app.logger.error(f"Error fetching system stats: {e}", exc_info=True)
        # Return error with mock data
        return jsonify({
            'error': str(e),
            'memory': {'percent': 50, 'used': 8, 'total': 16},
            'disk': {'percent': 45, 'used': 45, 'total': 100},
            'cpu': {'percent': 30},
            'uptime': 48
        })

# Add batch processing route for documents that were uploaded but not processed
@app.route('/process-documents', methods=['POST'])
def process_documents():
    """Process documents that were previously uploaded but not processed"""
    
    # Get parameters from form
    batch_size = request.form.get('batch_size', type=int) or 20
    doc_ids = request.form.getlist('doc_ids', type=int)
    
    if not doc_ids:
        # If no specific IDs provided, get all unprocessed documents
        unprocessed_docs = Document.query.filter_by(processed=False).filter(Document.processing_error.is_(None)).all()
        doc_ids = [doc.id for doc in unprocessed_docs]
    
    if not doc_ids:
        flash('No documents found to process.', 'warning')
        return redirect(url_for('documents'))
    
    # Add documents to processing queue
    added_count = doc_queue.add_documents(doc_ids)
    
    # Set batch size if provided
    if batch_size:
        doc_queue.batch_size = max(5, min(100, batch_size))
    
    # Start processing if not already running
    if not doc_queue.is_processing:
        doc_queue.start()
    
    flash(f'Added {added_count} documents to processing queue.', 'success')
    return redirect(url_for('documents'))

# Add a route to handle batch operations for documents
@app.route('/batch-action', methods=['POST'])
def batch_action():
    """Handle batch operations like delete, reprocess, etc."""
    
    action = request.form.get('action')
    doc_ids = request.form.getlist('doc_ids', type=int)
    
    if not doc_ids:
        flash('No documents selected.', 'warning')
        return redirect(url_for('documents'))
    
    if action == 'delete':
        # Delete selected documents
        deleted_count = 0
        for doc_id in doc_ids:
            try:
                document = Document.query.get(doc_id)
                if document:
                    # Delete file
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], document.filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    
                    # Delete from database
                    db.session.delete(document)
                    deleted_count += 1
            except Exception as e:
                app.logger.error(f"Error deleting document {doc_id}: {e}", exc_info=True)
        
        db.session.commit()
        flash(f'Deleted {deleted_count} documents.', 'success')
    
    elif action == 'reprocess':
        # Reset processing status and add to queue
        reset_count = 0
        for doc_id in doc_ids:
            try:
                document = Document.query.get(doc_id)
                if document:
                    document.processed = False
                    document.processing_error = None
                    db.session.commit()
                    reset_count += 1
            except Exception as e:
                app.logger.error(f"Error resetting document {doc_id}: {e}", exc_info=True)
        
        # Add to processing queue
        added_count = doc_queue.add_documents(doc_ids)
        
        # Start processing if not already running
        if not doc_queue.is_processing:
            doc_queue.start()
        
        flash(f'Reset {reset_count} documents and added them to processing queue.', 'success')
    
    elif action == 'export':
        # Export selected documents
        try:
            documents = Document.query.filter(Document.id.in_(doc_ids)).all()
            filepath = export_documents_to_excel(documents)
            
            if filepath:
                return send_file(filepath, as_attachment=True)
            else:
                flash('Failed to export documents.', 'danger')
        except Exception as e:
            app.logger.error(f"Error exporting documents: {e}", exc_info=True)
            flash(f'Error exporting documents: {e}', 'danger')
    
    return redirect(url_for('documents'))

# Add route for specialized bulk operations
@app.route('/bulk-operations', methods=['GET'])
def bulk_operations():
    """Show bulk operations interface"""
    # Count various document categories
    total_count = Document.query.count()
    processed_count = Document.query.filter_by(processed=True).count()
    unprocessed_count = Document.query.filter_by(processed=False).filter(Document.processing_error.is_(None)).count()
    error_count = Document.query.filter(Document.processing_error.isnot(None)).count()
    
    # Get queue status
    queue_status = doc_queue.get_status()
    
    # Recent documents with errors
    error_docs = Document.query.filter(Document.processing_error.isnot(None)).order_by(Document.upload_date.desc()).limit(5).all()
    
    return render_template('bulk_operations.html',
                          total_count=total_count,
                          processed_count=processed_count,
                          unprocessed_count=unprocessed_count,
                          error_count=error_count,
                          queue_status=queue_status,
                          error_docs=error_docs)

# Helper function for checking allowed file types
def allowed_file(filename, allowed_extensions):
    """Check if a file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Main entry point
if __name__ == '__main__':
    app.run(debug=True)
