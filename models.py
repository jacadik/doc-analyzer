from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import hashlib

db = SQLAlchemy()

# Association tables for many-to-many relationships
document_paragraph = db.Table('document_paragraph',
    db.Column('document_id', db.Integer, db.ForeignKey('document.id'), primary_key=True),
    db.Column('paragraph_id', db.Integer, db.ForeignKey('paragraph.id'), primary_key=True)
)

paragraph_similarity = db.Table('paragraph_similarity',
    db.Column('paragraph_id', db.Integer, db.ForeignKey('paragraph.id'), primary_key=True),
    db.Column('similar_paragraph_id', db.Integer, db.ForeignKey('paragraph.id'), primary_key=True),
    db.Column('similarity_score', db.Float)
)

document_variable = db.Table('document_variable',
    db.Column('document_id', db.Integer, db.ForeignKey('document.id'), primary_key=True),
    db.Column('variable_id', db.Integer, db.ForeignKey('variable.id'), primary_key=True),
    db.Column('count', db.Integer, default=1)
)

class Document(db.Model):
    """Document model representing an uploaded file"""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)  # 'pdf' or 'docx'
    file_size = db.Column(db.Integer, nullable=False)  # Size in bytes
    page_count = db.Column(db.Integer, default=0)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    processed = db.Column(db.Boolean, default=False)
    processing_error = db.Column(db.Text, nullable=True)
    
    # Raw extracted text
    full_text = db.Column(db.Text, nullable=True)
    
    # Layout information (JSON)
    layout_info = db.Column(db.Text, nullable=True)
    
    # Relationships
    paragraphs = db.relationship('Paragraph', secondary=document_paragraph, 
                               backref=db.backref('documents', lazy='dynamic'))
    variables = db.relationship('Variable', secondary=document_variable,
                              backref=db.backref('documents', lazy='dynamic'))
    
    def __repr__(self):
        return f'<Document {self.original_filename}>'
    
    @property
    def status(self):
        if self.processing_error:
            return 'error'
        elif self.processed:
            return 'processed'
        else:
            return 'processing'
    
    @property
    def paragraph_count(self):
        return len(self.paragraphs)
    
    @property
    def variable_count(self):
        return db.session.query(document_variable).filter_by(document_id=self.id).count()


class Paragraph(db.Model):
    """Paragraph model representing a text paragraph"""
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    hash = db.Column(db.String(64), index=True, nullable=False)
    position = db.Column(db.Integer, nullable=True)  # Position in document (optional)
    
    # Similar paragraphs
    similar_paragraphs = db.relationship(
        'Paragraph', 
        secondary=paragraph_similarity,
        primaryjoin=(paragraph_similarity.c.paragraph_id == id),
        secondaryjoin=(paragraph_similarity.c.similar_paragraph_id == id),
        backref=db.backref('similar_to', lazy='dynamic')
    )
    
    def __repr__(self):
        return f'<Paragraph {self.id} {self.text[:20]}...>'
    
    @staticmethod
    def generate_hash(text):
        """Generate a hash for a paragraph text"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def add_similar_paragraph(self, paragraph, score):
        """Add a similar paragraph with similarity score"""
        # Check if relationship already exists
        existing = db.session.query(paragraph_similarity).filter_by(
            paragraph_id=self.id, 
            similar_paragraph_id=paragraph.id
        ).first()
        
        if existing:
            # Update score if relationship exists
            existing.similarity_score = score
        else:
            # Add new relationship
            db.session.execute(paragraph_similarity.insert().values(
                paragraph_id=self.id,
                similar_paragraph_id=paragraph.id,
                similarity_score=score
            ))
    
    def get_similarity_score(self, paragraph):
        """Get similarity score between this paragraph and another"""
        result = db.session.query(paragraph_similarity.c.similarity_score).filter(
            paragraph_similarity.c.paragraph_id == self.id,
            paragraph_similarity.c.similar_paragraph_id == paragraph.id
        ).first()
        
        if result:
            return result[0]
        return 0
    
    @property
    def document_count(self):
        """Count documents containing this paragraph"""
        return self.documents.count()


class Variable(db.Model):
    """Variable model representing a placeholder like <<variable>>"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    pattern_type = db.Column(db.String(20), nullable=False)  # e.g., '<<>>', '{{}}', '${}'
    
    def __repr__(self):
        return f'<Variable {self.pattern_type}{self.name}>'
    
    @property
    def full_name(self):
        """Return the variable with its pattern markers"""
        if self.pattern_type == '<<>>':
            return f'<<{self.name}>>'
        elif self.pattern_type == '{{}}':
            return f'{{{{{self.name}}}}}'
        elif self.pattern_type == '${}':
            return f'${{{self.name}}}'
        else:
            return self.name
    
    @property
    def document_count(self):
        """Count documents containing this variable"""
        return self.documents.count()
