import pandas as pd
import os
import logging
from datetime import datetime

# Set up logger
logger = logging.getLogger(__name__)

def export_documents_to_excel(documents, export_dir='exports'):
    """Export documents summary to Excel file"""
    try:
        # Create exports directory if it doesn't exist
        os.makedirs(export_dir, exist_ok=True)
        
        # Generate timestamp for filename
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"documents_export_{timestamp}.xlsx"
        filepath = os.path.join(export_dir, filename)
        
        # Create Excel writer
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Document Summary Sheet
            doc_data = [{
                'ID': doc.id,
                'Filename': doc.original_filename,
                'File Type': doc.file_type,
                'File Size (KB)': round(doc.file_size / 1024, 2),
                'Pages': doc.page_count,
                'Paragraphs': len(doc.paragraphs),
                'Variables': doc.variable_count,
                'Upload Date': doc.upload_date,
                'Status': doc.status
            } for doc in documents]
            
            doc_df = pd.DataFrame(doc_data)
            doc_df.to_excel(writer, sheet_name='Document Summary', index=False)
            
            # Format the sheet
            worksheet = writer.sheets['Document Summary']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"Document summary exported to {filepath}")
        return filepath
    
    except Exception as e:
        logger.error(f"Error exporting documents to Excel: {e}", exc_info=True)
        return None

def export_analysis_to_excel(document, paragraphs, variables, similar_paragraphs, export_dir='exports'):
    """Export detailed analysis of a single document to Excel"""
    try:
        # Create exports directory if it doesn't exist
        os.makedirs(export_dir, exist_ok=True)
        
        # Generate timestamp for filename
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        safe_filename = document.original_filename.replace(' ', '_')
        filename = f"analysis_{safe_filename}_{timestamp}.xlsx"
        filepath = os.path.join(export_dir, filename)
        
        # Create Excel writer
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Document Info Sheet
            doc_info = [{
                'Property': 'Filename',
                'Value': document.original_filename
            }, {
                'Property': 'File Type',
                'Value': document.file_type
            }, {
                'Property': 'File Size (KB)',
                'Value': round(document.file_size / 1024, 2)
            }, {
                'Property': 'Pages',
                'Value': document.page_count
            }, {
                'Property': 'Paragraph Count',
                'Value': len(paragraphs)
            }, {
                'Property': 'Variable Count',
                'Value': len(variables)
            }, {
                'Property': 'Upload Date',
                'Value': document.upload_date
            }]
            
            doc_df = pd.DataFrame(doc_info)
            doc_df.to_excel(writer, sheet_name='Document Info', index=False)
            
            # Paragraphs Sheet
            para_data = [{
                'Position': i+1,
                'Length': len(p.text),
                'Text': p.text[:500] + ('...' if len(p.text) > 500 else ''),
                'Document Count': p.document_count
            } for i, p in enumerate(paragraphs)]
            
            para_df = pd.DataFrame(para_data)
            para_df.to_excel(writer, sheet_name='Paragraphs', index=False)
            
            # Variables Sheet
            var_data = [{
                'Name': v.name,
                'Pattern': v.pattern_type,
                'Full Format': v.full_name,
                'Document Count': v.document_count
            } for v in variables]
            
            var_df = pd.DataFrame(var_data)
            var_df.to_excel(writer, sheet_name='Variables', index=False)
            
            # Similar Paragraphs Sheet
            if similar_paragraphs:
                similar_data = [{
                    'Paragraph 1': sp[0].text[:200] + ('...' if len(sp[0].text) > 200 else ''),
                    'Paragraph 2': sp[1].text[:200] + ('...' if len(sp[1].text) > 200 else ''),
                    'Similarity Score': sp[2]
                } for sp in similar_paragraphs]
                
                similar_df = pd.DataFrame(similar_data)
                similar_df.to_excel(writer, sheet_name='Similar Paragraphs', index=False)
            
            # Format all sheets
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(cell.value)
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 100)  # Cap width at 100
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"Document analysis exported to {filepath}")
        return filepath
    
    except Exception as e:
        logger.error(f"Error exporting analysis to Excel: {e}", exc_info=True)
        return None

def export_templates_to_excel(documents, export_dir='exports'):
    """Export template analysis data to Excel"""
    try:
        # Create exports directory if it doesn't exist
        os.makedirs(export_dir, exist_ok=True)
        
        # Generate timestamp for filename
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"template_analysis_{timestamp}.xlsx"
        filepath = os.path.join(export_dir, filename)
        
        # Group documents by similar layouts (this is simplified)
        # In a real implementation, we would need more sophisticated layout comparison
        templates = {}
        for doc in documents:
            # For this example, we'll group by page count (very simplified)
            key = f"Template {doc.page_count} pages"
            if key in templates:
                templates[key].append(doc)
            else:
                templates[key] = [doc]
        
        # Create Excel writer
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Templates Summary Sheet
            template_data = [{
                'Template Name': template_name,
                'Document Count': len(docs),
                'Example Document': docs[0].original_filename if docs else 'None'
            } for template_name, docs in templates.items()]
            
            template_df = pd.DataFrame(template_data)
            template_df.to_excel(writer, sheet_name='Templates Summary', index=False)
            
            # Template Documents Sheet
            docs_list = []
            for template_name, docs in templates.items():
                for doc in docs:
                    docs_list.append({
                        'Template Name': template_name,
                        'Document ID': doc.id,
                        'Filename': doc.original_filename,
                        'File Type': doc.file_type,
                        'Pages': doc.page_count,
                        'Paragraphs': len(doc.paragraphs),
                        'Variables': doc.variable_count
                    })
            
            docs_df = pd.DataFrame(docs_list)
            docs_df.to_excel(writer, sheet_name='Template Documents', index=False)
            
            # Format all sheets
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(cell.value)
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 100)  # Cap width at 100
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"Template analysis exported to {filepath}")
        return filepath
    
    except Exception as e:
        logger.error(f"Error exporting templates to Excel: {e}", exc_info=True)
        return None

def export_variables_to_excel(variables, export_dir='exports'):
    """Export variables summary to Excel"""
    try:
        # Create exports directory if it doesn't exist
        os.makedirs(export_dir, exist_ok=True)
        
        # Generate timestamp for filename
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"variables_export_{timestamp}.xlsx"
        filepath = os.path.join(export_dir, filename)
        
        # Create Excel writer
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Variables Sheet
            var_data = [{
                'Name': var.name,
                'Pattern': var.pattern_type,
                'Full Format': var.full_name,
                'Document Count': var.document_count
            } for var in variables]
            
            var_df = pd.DataFrame(var_data)
            var_df.to_excel(writer, sheet_name='Variables', index=False)
            
            # Format the sheet
            worksheet = writer.sheets['Variables']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except:
                        pass
                adjusted_width = min(max_length + 2, 100)  # Cap width at 100
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        logger.info(f"Variables exported to {filepath}")
        return filepath
    
    except Exception as e:
        logger.error(f"Error exporting variables to Excel: {e}", exc_info=True)
        return None
