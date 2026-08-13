import os
import re
from django.core.management.base import BaseCommand
from accounts.models import LegalDocument

class Command(BaseCommand):
    help = 'Seeds legal documents from HTML files'

    def extract_main_content(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extract everything inside <main>...</main>
            match = re.search(r'<main[^>]*>(.*?)</main>', content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
            else:
                self.stdout.write(self.style.WARNING(f"No <main> tag found in {filepath}"))
                return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading {filepath}: {e}"))
            return None

    def seed_document(self, filepath, doc_type, title):
        self.stdout.write(f"Processing {filepath} for {doc_type}...")
        html_content = self.extract_main_content(filepath)
        
        if not html_content:
            return False
            
        # Delete existing docs of this type to ensure we only have one active one
        LegalDocument.objects.filter(doc_type=doc_type).delete()
        
        LegalDocument.objects.create(
            doc_type=doc_type,
            title=title,
            content=html_content,
            is_active=True,
            version='1.0'
        )
        
        self.stdout.write(self.style.SUCCESS(f"Seeded {doc_type} document successfully."))
        return True

    def handle(self, *args, **options):
        # Go up 5 levels from seed_legal_docs.py to reach /home/afari/Projects/ns
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        terms_path = os.path.join(project_root, 'terms.html')
        privacy_path = os.path.join(project_root, 'privacy.html')
        
        success_terms = False
        if os.path.exists(terms_path):
            success_terms = self.seed_document(terms_path, 'TERMS', 'Terms & Conditions')
        else:
            self.stdout.write(self.style.WARNING(f"File not found: {terms_path}"))
            
        success_privacy = False
        if os.path.exists(privacy_path):
            success_privacy = self.seed_document(privacy_path, 'PRIVACY', 'Privacy Policy')
        else:
            self.stdout.write(self.style.WARNING(f"File not found: {privacy_path}"))
        
        if success_terms or success_privacy:
            self.stdout.write(self.style.SUCCESS("Successfully seeded all legal documents!"))
        else:
            self.stdout.write(self.style.WARNING("Some errors occurred during seeding."))
