import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_bootstrap import Bootstrap5
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import SubmitField
from werkzeug.utils import secure_filename
from config import Config
from models import db, Document, Paragraph, Variable, document_paragraph, document_variable, paragraph_similarity
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

# Create and configure Flask app
app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

# Initialize extensions
bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)
db.init_app(app)

# Create background processing queue
processing_queue = []
background_thread = None
is_processing = False

def process_document_background():
    """Background thread for processing documents"""
    global is_processing
    
    while True:
        if processing_queue:
            is_processing = True
            document_id = processing_queue.pop(0)
            
            try:
                app.logger.info(f"Processing document ID {document_id}")
                
                # Get document from database
                with app.app_context():
                    document = Document.query.get(document_id)
                    if not document:
                        app.logger.error(f"Document {document_id} not found")
                        continue
                    
                    # Get file path
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], document.filename)
                    if not os.path.exists(file_path):
                        error_msg = f"File {file_path} does not exist"
                        app.logger.error(error_msg)
                        document.processing_error = error_msg
                        db.session.commit()
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
                    
                    app.logger.info(f"Document {document_id} processed successfully")
            
            except Exception as e:
                app.logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
                # Update document status
                with app.app_context():
                    document = Document.query.get(document_id)
                    if document:
                        document.processing_error = str(e)
                        db.session.commit()
        
        else:
            is_processing = False
            time.sleep(1)  # Sleep when queue is empty

def start_background_thread():
    """Start the background processing thread if not already running"""
    global background_thread
    
    if background_thread is None or not background_thread.is_alive():
        background_thread = threading.Thread(target=process_document_background)
        background_thread.daemon = True
        background_thread.start()

# Create database tables and initialize app
# Replacing @app.before_first_request which is removed in Flask 2.x
def create_tables():
    db.create_all()
    # Ensure export directory exists
    os.makedirs('exports', exist_ok=True)
    # Start background processing thread
    start_background_thread()

# Initialize the app with a context
with app.app_context():
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
    """Upload document page"""
    form = UploadForm()
    
    if form.validate_on_submit():
        file = form.file.data
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
            
            # Add to processing queue
            processing_queue.append(document.id)
            start_background_thread()
            
            flash(f'Document {result["original_filename"]} uploaded successfully!', 'success')
            return redirect(url_for('documents'))
        
        flash('Failed to upload document.', 'danger')
    
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
    
    # Check if background thread is running
    thread_active = background_thread is not None and background_thread.is_alive()
    
    return jsonify({
        'total': total,
        'processed': processed,
        'processing': processing,
        'error': error,
        'queue_length': len(processing_queue),
        'thread_active': thread_active,
        'is_processing': is_processing
    })

# Main entry point
if __name__ == '__main__':
    app.run(debug=True)
