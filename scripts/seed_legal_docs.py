import os
import django
import re

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ns_backend.settings')
django.setup()

from accounts.models import LegalDocument

def extract_main_content(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract everything inside <main>...</main>
        match = re.search(r'<main[^>]*>(.*?)</main>', content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        else:
            print(f"No <main> tag found in {filepath}")
            return None
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None

def seed_document(filepath, doc_type, title):
    print(f"Processing {filepath} for {doc_type}...")
    html_content = extract_main_content(filepath)
    
    if not html_content:
        return False
        
    # Create or update the document
    # Delete existing docs of this type to ensure we only have one active one for simplicity
    LegalDocument.objects.filter(doc_type=doc_type).delete()
    
    doc = LegalDocument.objects.create(
        doc_type=doc_type,
        title=title,
        content=html_content,
        is_active=True,
        version='1.0'
    )
    
    print(f"Seeded {doc_type} document successfully.")
    return True

if __name__ == '__main__':
    base_dir = '/home/afari/Projects/ns'
    
    terms_path = os.path.join(base_dir, 'terms.html')
    privacy_path = os.path.join(base_dir, 'privacy.html')
    
    success_terms = seed_document(terms_path, 'TERMS', 'Terms & Conditions')
    success_privacy = seed_document(privacy_path, 'PRIVACY', 'Privacy Policy')
    
    if success_terms and success_privacy:
        print("Successfully seeded all legal documents!")
    else:
        print("Some errors occurred during seeding.")
