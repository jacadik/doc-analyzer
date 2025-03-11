import logging
import numpy as np
from fuzzywuzzy import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

# Set up logger
logger = logging.getLogger(__name__)

def preprocess_text(text):
    """Preprocess text for similarity comparison"""
    # Convert to lowercase
    text = text.lower()
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove common punctuation that doesn't affect meaning
    text = re.sub(r'[,.;:!?"\']', '', text)
    
    return text

def find_exact_duplicates(paragraphs):
    """Find exact duplicate paragraphs using hash comparison"""
    # Group paragraphs by hash
    hash_groups = {}
    
    for para in paragraphs:
        para_hash = para['hash']
        if para_hash in hash_groups:
            hash_groups[para_hash].append(para)
        else:
            hash_groups[para_hash] = [para]
    
    # Filter to only groups with multiple paragraphs (duplicates)
    duplicate_groups = {h: paras for h, paras in hash_groups.items() if len(paras) > 1}
    
    logger.info(f"Found {len(duplicate_groups)} groups of exact duplicate paragraphs")
    
    return duplicate_groups

def find_similar_paragraphs(paragraphs, similarity_threshold=0.8, max_comparisons=10000):
    """Find similar (but not exact) paragraphs using TF-IDF and cosine similarity"""
    # Skip if too few paragraphs
    if len(paragraphs) < 2:
        return []
    
    # Extract text for vectorization
    texts = [preprocess_text(p['text']) for p in paragraphs]
    
    # Generate TF-IDF vectors
    vectorizer = TfidfVectorizer(min_df=1, stop_words='english')
    try:
        tfidf_matrix = vectorizer.fit_transform(texts)
    except ValueError as e:
        logger.error(f"Error in TF-IDF vectorization: {e}")
        return []
    
    # Calculate cosine similarity
    logger.info("Calculating paragraph similarities...")
    similar_pairs = []
    
    # Limit number of comparisons to avoid memory issues with large documents
    n_paragraphs = len(paragraphs)
    n_comparisons = n_paragraphs * (n_paragraphs - 1) // 2
    
    if n_comparisons > max_comparisons:
        logger.warning(f"Too many paragraph comparisons ({n_comparisons}). Using sampling.")
        # Sample pairs instead of computing full similarity matrix
        indices = list(range(n_paragraphs))
        sample_size = min(1000, n_paragraphs)  # Sample at most 1000 paragraphs
        sample_indices = np.random.choice(indices, size=sample_size, replace=False)
        
        for i in range(len(sample_indices)):
            idx1 = sample_indices[i]
            for j in range(i+1, len(sample_indices)):
                idx2 = sample_indices[j]
                # Skip if hashes are the same (exact duplicates)
                if paragraphs[idx1]['hash'] == paragraphs[idx2]['hash']:
                    continue
                
                # Calculate similarity between these two paragraphs
                sim = cosine_similarity(tfidf_matrix[idx1:idx1+1], tfidf_matrix[idx2:idx2+1])[0][0]
                
                # Check if similarity is above threshold
                if sim >= similarity_threshold:
                    # Confirm with fuzzy matching
                    fuzzy_sim = fuzz.ratio(texts[idx1], texts[idx2]) / 100.0
                    
                    # Take average of both similarity measures
                    combined_sim = (sim + fuzzy_sim) / 2
                    
                    if combined_sim >= similarity_threshold:
                        similar_pairs.append({
                            'para1': paragraphs[idx1],
                            'para2': paragraphs[idx2],
                            'similarity': combined_sim
                        })
    else:
        # Compute full pairwise similarity
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Find similar pairs
        for i in range(n_paragraphs):
            for j in range(i+1, n_paragraphs):
                # Skip if hashes are the same (exact duplicates)
                if paragraphs[i]['hash'] == paragraphs[j]['hash']:
                    continue
                
                sim = similarity_matrix[i, j]
                
                # Check if similarity is above threshold
                if sim >= similarity_threshold:
                    # Confirm with fuzzy matching
                    fuzzy_sim = fuzz.ratio(texts[i], texts[j]) / 100.0
                    
                    # Take average of both similarity measures
                    combined_sim = (sim + fuzzy_sim) / 2
                    
                    if combined_sim >= similarity_threshold:
                        similar_pairs.append({
                            'para1': paragraphs[i],
                            'para2': paragraphs[j],
                            'similarity': combined_sim
                        })
    
    logger.info(f"Found {len(similar_pairs)} similar paragraph pairs")
    return similar_pairs

def analyze_variable_usage(variables):
    """Analyze variable usage patterns"""
    # Count variable occurrences by name
    var_counts = {}
    for var in variables:
        name = var['name']
        if name in var_counts:
            var_counts[name]['count'] += 1
        else:
            var_counts[name] = {
                'count': 1,
                'pattern_type': var['pattern_type']
            }
    
    # Sort by frequency
    sorted_vars = sorted(var_counts.items(), key=lambda x: x[1]['count'], reverse=True)
    
    # Return sorted list of variables with counts
    result = [
        {
            'name': name,
            'pattern_type': data['pattern_type'],
            'count': data['count']
        }
        for name, data in sorted_vars
    ]
    
    logger.info(f"Analyzed {len(result)} distinct variables")
    return result

def get_paragraph_statistics(paragraphs):
    """Generate statistics about paragraphs"""
    # Skip if no paragraphs
    if not paragraphs:
        return {}
    
    # Calculate paragraph lengths
    lengths = [len(p['text']) for p in paragraphs]
    
    # Calculate statistics
    stats = {
        'count': len(paragraphs),
        'avg_length': sum(lengths) / len(lengths),
        'min_length': min(lengths),
        'max_length': max(lengths),
        'total_chars': sum(lengths)
    }
    
    return stats

def extract_common_phrases(paragraphs, min_phrase_length=30, max_phrases=20):
    """Extract common phrases across paragraphs"""
    # Skip if too few paragraphs
    if len(paragraphs) < 5:
        return []
    
    # Extract text
    texts = [p['text'] for p in paragraphs]
    
    # Extract all n-grams of words from each paragraph
    all_phrases = []
    for text in texts:
        words = text.split()
        if len(words) < 5:  # Skip very short paragraphs
            continue
            
        # Generate phrases of different lengths
        for i in range(len(words) - 4):  # At least 5 words
            for j in range(i + 4, min(i + 15, len(words))):  # Max 15 words
                phrase = ' '.join(words[i:j+1])
                if len(phrase) >= min_phrase_length:
                    all_phrases.append(phrase)
    
    # Count occurrences of each phrase
    phrase_counts = {}
    for phrase in all_phrases:
        if phrase in phrase_counts:
            phrase_counts[phrase] += 1
        else:
            phrase_counts[phrase] = 1
    
    # Filter to phrases that appear multiple times
    common_phrases = [(phrase, count) for phrase, count in phrase_counts.items() if count > 1]
    
    # Sort by frequency
    common_phrases.sort(key=lambda x: x[1], reverse=True)
    
    # Limit to top phrases and remove overlapping ones
    filtered_phrases = []
    for phrase, count in common_phrases[:100]:  # Check top 100 candidates
        # Check if this phrase is contained in any we've already selected
        is_contained = False
        for selected_phrase, _ in filtered_phrases:
            if phrase in selected_phrase:
                is_contained = True
                break
        
        if not is_contained:
            filtered_phrases.append((phrase, count))
        
        if len(filtered_phrases) >= max_phrases:
            break
    
    logger.info(f"Extracted {len(filtered_phrases)} common phrases")
    return filtered_phrases
